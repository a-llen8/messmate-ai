from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from app.core.database import get_db
from app.api.deps import get_current_user, get_caterer
from app.models.models import (
    User, Menu, Subscription, SubscriptionRequest,
    Complaint, Attendance, MessInfo, SlotType,
    SubStatus, RequestStatus, RequestType
)

router = APIRouter(prefix="/caterer", tags=["caterer"])

# ── Dashboard ────────────────────────────────────────────────
@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    today = date.today()
    total_students  = db.query(User).filter(User.role == "student").count()
    active_subs     = db.query(Subscription).filter(Subscription.status == SubStatus.active).count()
    today_attendance = db.query(Attendance).filter(Attendance.date == today).count()
    open_complaints = db.query(Complaint).filter(Complaint.status == "open").count()
    pending_requests = db.query(SubscriptionRequest).filter(SubscriptionRequest.status == RequestStatus.pending).count()

    return {
        "total_students":   total_students,
        "active_subs":      active_subs,
        "today_attendance": today_attendance,
        "open_complaints":  open_complaints,
        "pending_requests": pending_requests,
    }

# ── Menu ─────────────────────────────────────────────────────
class MenuCreate(BaseModel):
    date: date
    slot: SlotType
    items: str
    nutrition_json: Optional[str] = None

@router.post("/menu")
def create_menu(
    payload: MenuCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    existing = db.query(Menu).filter(
        Menu.date == payload.date,
        Menu.slot == payload.slot
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Menu already exists for this slot")

    menu = Menu(
        date           = payload.date,
        slot           = payload.slot,
        items          = payload.items,
        nutrition_json = payload.nutrition_json,
    )
    db.add(menu)
    db.commit()
    db.refresh(menu)
    return {"message": "Menu created", "menu_id": menu.id}

@router.put("/menu/{menu_id}")
def update_menu(
    menu_id: int,
    payload: MenuCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")

    menu.items          = payload.items
    menu.nutrition_json = payload.nutrition_json
    db.commit()
    return {"message": "Menu updated"}

@router.get("/menu")
def list_menus(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    today = date.today()
    menus = db.query(Menu).filter(Menu.date == today).all()
    return [
        {
            "id":    m.id,
            "slot":  m.slot,
            "items": m.items,
            "date":  m.date,
        }
        for m in menus
    ]

# ── Subscriptions ─────────────────────────────────────────────
@router.get("/subscriptions/requests")
def get_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    requests = db.query(SubscriptionRequest).filter(
        SubscriptionRequest.status == RequestStatus.pending
    ).all()
    return [
        {
            "id":        r.id,
            "user_id":   r.user_id,
            "type":      r.type,
            "plan_type": r.plan_type,
            "created_at": r.created_at,
        }
        for r in requests
    ]

@router.post("/subscriptions/requests/{request_id}/approve")
def approve_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    req = db.query(SubscriptionRequest).filter(SubscriptionRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    req.status = RequestStatus.approved

    if req.type == RequestType.new:
        sub = Subscription(
            user_id    = req.user_id,
            plan_type  = req.plan_type,
            status     = SubStatus.active,
            start_date = date.today(),
            locked_price = 0,  # caterer sets price separately
        )
        db.add(sub)

    elif req.type == RequestType.cancel:
        sub = db.query(Subscription).filter(
            Subscription.user_id == req.user_id
        ).first()
        if sub:
            sub.status = SubStatus.cancelled

    db.commit()
    return {"message": f"Request {request_id} approved"}

@router.post("/subscriptions/requests/{request_id}/reject")
def reject_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    req = db.query(SubscriptionRequest).filter(SubscriptionRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    req.status = RequestStatus.rejected
    db.commit()
    return {"message": f"Request {request_id} rejected"}

# ── Complaints ────────────────────────────────────────────────
@router.get("/complaints")
def get_complaints(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    complaints = db.query(Complaint).filter(Complaint.status == "open").all()
    return [
        {
            "id":       c.id,
            "user_id":  c.user_id,
            "text":     c.text,
            "category": c.category,
            "created_at": c.created_at,
        }
        for c in complaints
    ]

@router.put("/complaints/{complaint_id}/resolve")
def resolve_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint.status = "resolved"
    db.commit()
    return {"message": "Complaint resolved"}

# ── Mess Info ─────────────────────────────────────────────────
class MessInfoUpdate(BaseModel):
    key: str
    value: str

@router.post("/mess-info")
def update_mess_info(
    payload: MessInfoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    info = db.query(MessInfo).filter(MessInfo.key == payload.key).first()
    if info:
        info.value = payload.value
    else:
        info = MessInfo(key=payload.key, value=payload.value)
        db.add(info)
    db.commit()
    return {"message": f"Mess info '{payload.key}' updated"}

# ── Attendance ────────────────────────────────────────────────
@router.get("/attendance")
def get_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    today = date.today()
    records = db.query(Attendance).filter(Attendance.date == today).all()
    return [
        {
            "id":         r.id,
            "user_id":    r.user_id,
            "slot":       r.slot,
            "scanned_at": r.scanned_at,
        }
        for r in records
    ]