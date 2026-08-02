import hmac
import hashlib
import qrcode
import io
import base64
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.config import settings, SLOT_WINDOWS, PLAN_SLOTS
from app.api.deps import get_current_user, get_caterer
from app.models.models import User, Attendance, Menu, Subscription, SubStatus, SlotType

router = APIRouter(prefix="/qr", tags=["qr"])


def current_slot() -> str | None:
    """Return the slot name if right now falls inside one of the serving
    windows, otherwise None."""
    now = datetime.now().time()
    for slot_name, (start, end) in SLOT_WINDOWS.items():
        if start <= now <= end:
            return slot_name
    return None


# ── Generate QR token ─────────────────────────────────────────
def generate_token(user_id: int, date_str: str) -> str:
    message = f"{user_id}:{date_str}:{settings.QR_SEMESTER}"
    token = hmac.new(
        settings.QR_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return token

# ── Generate QR image ─────────────────────────────────────────
@router.get("/generate")
def generate_qr(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # check active subscription
    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status  == SubStatus.active
    ).first()
    if not sub:
        raise HTTPException(status_code=403, detail="No active subscription")

    slot_now = current_slot()
    if slot_now and slot_now not in PLAN_SLOTS.get(sub.plan_type, set()):
        raise HTTPException(status_code=403, detail=f"Your plan doesn't include {slot_now}")

    today    = date.today()
    date_str = today.isoformat()
    token    = generate_token(current_user.id, date_str)

    # generate QR image — one per student per day, slot decided at scan time
    qr_data = f"{current_user.id}:{date_str}:{token}"
    img     = qrcode.make(qr_data)
    buf     = io.BytesIO()
    img.save(buf, format="PNG")
    b64     = base64.b64encode(buf.getvalue()).decode()

    return {
        "qr_base64": b64,
        "token":     token,
        "date":      date_str,
    }

# ── Scan QR ───────────────────────────────────────────────────
class ScanRequest(BaseModel):
    qr_data: str

@router.post("/scan")
def scan_qr(
    payload: ScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    try:
        parts    = payload.qr_data.split(":")
        user_id  = int(parts[0])
        date_str = parts[1]
        token    = parts[2]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid QR data")

    # verify token
    expected = generate_token(user_id, date_str)
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid QR token")

    # check date
    if date_str != date.today().isoformat():
        raise HTTPException(status_code=400, detail="QR expired — wrong date")

    # decide slot from current time
    slot = current_slot()
    if slot is None:
        raise HTTPException(status_code=400, detail="No meal is being served right now")

    sub = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.status == SubStatus.active,
    ).first()
    if not sub or slot not in PLAN_SLOTS.get(sub.plan_type, set()):
        raise HTTPException(status_code=403, detail=f"This student's plan doesn't include {slot}")

    # check already scanned for this slot today
    existing = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date    == date.today(),
        Attendance.slot    == slot
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Already scanned for {slot}")

    # get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # get menu
    menu = db.query(Menu).filter(
        Menu.date == date.today(),
        Menu.slot == slot
    ).first()

    # record attendance
    attendance = Attendance(
        user_id   = user_id,
        menu_id   = menu.id if menu else None,
        date      = date.today(),
        slot      = slot,
        qr_token  = token,
    )
    db.add(attendance)
    db.commit()

    return {
        "message": "Attendance recorded",
        "student": user.name,
        "slot":    slot,
    }


class ManualAttendanceRequest(BaseModel):
    user_id: int


@router.post("/manual")
def mark_present_manually(
    payload: ManualAttendanceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    slot = current_slot()
    if slot is None:
        raise HTTPException(status_code=400, detail="No meal is being served right now")

    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Student not found")

    sub = db.query(Subscription).filter(
        Subscription.user_id == payload.user_id,
        Subscription.status == SubStatus.active,
    ).first()
    if not sub or slot not in PLAN_SLOTS.get(sub.plan_type, set()):
        raise HTTPException(status_code=403, detail=f"This student's plan doesn't include {slot}")

    existing = db.query(Attendance).filter(
        Attendance.user_id == payload.user_id,
        Attendance.date == date.today(),
        Attendance.slot == slot,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Already scanned for {slot}")

    menu = db.query(Menu).filter(
        Menu.date == date.today(),
        Menu.slot == slot,
    ).first()

    attendance = Attendance(
        user_id=payload.user_id,
        menu_id=menu.id if menu else None,
        date=date.today(),
        slot=slot,
        qr_token="manual",
    )
    db.add(attendance)
    db.commit()

    return {
        "message": "Attendance recorded manually",
        "student": user.name,
        "slot": slot,
    }

# ── Fallback: name search ─────────────────────────────────────
@router.get("/search")
def search_student(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    students = db.query(User).filter(
        User.name.ilike(f"%{name}%"),
        User.role == "student"
    ).all()
    return [
        {
            "id":    s.id,
            "name":  s.name,
            "email": s.email,
        }
        for s in students
    ]