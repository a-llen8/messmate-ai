from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date
from app.core.database import get_db
from app.core.config import PLAN_SLOTS
from app.api.deps import get_current_user
from app.models.models import User, Subscription, SubscriptionRequest, Menu, Complaint, Rating, SubStatus, RequestType, RequestStatus, PricePlan

router = APIRouter(prefix="/student", tags=["student"])

# ── Profile ─────────────────────────────────────────────────
class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None

@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id":    current_user.id,
        "name":  current_user.name,
        "email": current_user.email,
        "phone": current_user.phone,
        "role":  current_user.role,
    }

@router.put("/profile")
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if payload.name:
        current_user.name = payload.name
    if payload.phone:
        current_user.phone = payload.phone
    db.commit()
    return {"message": "Profile updated"}

@router.get("/price-plans")
def get_price_plans(db: Session = Depends(get_db)):
    plans = db.query(PricePlan).all()
    return [{"plan_type": p.plan_type, "monthly_price": str(p.monthly_price)} for p in plans]

# ── Subscription ─────────────────────────────────────────────
class SubRequest(BaseModel):
    plan_type: str
    start_date: date
    end_date: date

@router.get("/price-preview")
def price_preview(
    plan_type: str,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    days = (end_date - start_date).days + 1
    if days < 7:
        raise HTTPException(status_code=400, detail="Minimum 7 days required")

    plan = db.query(PricePlan).filter(PricePlan.plan_type == plan_type).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Price not set for this plan yet")

    daily_rate = float(plan.monthly_price) / 30
    price = round(daily_rate * days, 2)

    return {"days": days, "monthly_price": str(plan.monthly_price), "calculated_price": price}

@router.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub:
        return {"status": "no subscription"}
    return {
        "plan_type":    sub.plan_type,
        "status":       sub.status,
        "start_date":   sub.start_date,
        "end_date":     sub.end_date,
        "locked_price": str(sub.locked_price),
    }

@router.post("/subscription/request")
def request_subscription(
    payload: SubRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if payload.start_date < date.today():
        raise HTTPException(status_code=400, detail="Start date cannot be in the past")

    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    days = (payload.end_date - payload.start_date).days + 1
    if days < 7:
        raise HTTPException(status_code=400, detail="Minimum 7 days required")

    existing = db.query(SubscriptionRequest).filter(
        SubscriptionRequest.user_id == current_user.id,
        SubscriptionRequest.status  == RequestStatus.pending,
        SubscriptionRequest.type    == RequestType.new
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Pending request already exists")

    req = SubscriptionRequest(
        user_id    = current_user.id,
        type       = RequestType.new,
        plan_type  = payload.plan_type,
        start_date = payload.start_date,
        end_date   = payload.end_date,
        status     = RequestStatus.pending,
    )
    db.add(req)
    db.commit()
    return {"message": "Subscription request submitted"}

@router.post("/subscription/cancel")
def cancel_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub or sub.status != SubStatus.active:
        raise HTTPException(status_code=400, detail="No active subscription")

    req = SubscriptionRequest(
        user_id = current_user.id,
        type    = RequestType.cancel,
        status  = RequestStatus.pending,
    )
    db.add(req)
    db.commit()
    return {"message": "Cancellation request submitted"}

# ── Menu ─────────────────────────────────────────────────────
@router.get("/menu/today")
def get_today_menu(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    today = date.today()
    menus = db.query(Menu).filter(Menu.date == today).all()
    if not menus:
        return {"message": "No menu for today"}

    result = []
    for m in menus:
        existing = db.query(Rating).filter(
            Rating.user_id == current_user.id,
            Rating.menu_id == m.id
        ).first()
        result.append({
            "id":        m.id,
            "slot":      m.slot,
            "items":     m.items,
            "my_rating": existing.score if existing else None,
        })
    return result

# ── Complaints ───────────────────────────────────────────────
class ComplaintRequest(BaseModel):
    text: str
    category: Optional[str] = None

@router.post("/complaint")
def submit_complaint(
    payload: ComplaintRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == SubStatus.active
    ).first()
    if not sub:
        raise HTTPException(status_code=403, detail="Active subscription required to file complaints")

    complaint = Complaint(
        user_id  = current_user.id,
        text     = payload.text,
        category = payload.category,
        status   = "open",
    )
    db.add(complaint)
    db.commit()
    return {"message": "Complaint submitted"}

# ── Ratings ──────────────────────────────────────────────────
class RatingRequest(BaseModel):
    menu_id: int
    score: int
    comment: Optional[str] = None

@router.post("/rating")
def submit_rating(
    payload: RatingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if payload.score < 1 or payload.score > 5:
        raise HTTPException(status_code=400, detail="Score must be 1-5")

    menu = db.query(Menu).filter(Menu.id == payload.menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu item not found")

    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == SubStatus.active
    ).first()
    if not sub or menu.slot not in PLAN_SLOTS.get(sub.plan_type, set()):
        raise HTTPException(status_code=403, detail=f"Your plan doesn't include {menu.slot}")

    existing = db.query(Rating).filter(
        Rating.user_id == current_user.id,
        Rating.menu_id == payload.menu_id
    ).first()

    if existing:
        existing.score = payload.score
        if payload.comment is not None:
            existing.comment = payload.comment
    else:
        rating = Rating(
            user_id = current_user.id,
            menu_id = payload.menu_id,
            score   = payload.score,
            comment = payload.comment,
        )
        db.add(rating)

    db.commit()
    return {"message": "Rating submitted"}