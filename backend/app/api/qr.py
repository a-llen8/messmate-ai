import hmac
import hashlib
import qrcode
import io
import base64
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date
from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_current_user, get_caterer
from app.models.models import User, Attendance, Menu, Subscription, SubStatus, SlotType

router = APIRouter(prefix="/qr", tags=["qr"])

# ── Generate QR token ─────────────────────────────────────────
def generate_token(user_id: int, slot: str, date_str: str) -> str:
    message = f"{user_id}:{slot}:{date_str}:{settings.QR_SEMESTER}"
    token = hmac.new(
        settings.QR_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return token

# ── Generate QR image ─────────────────────────────────────────
@router.get("/generate/{slot}")
def generate_qr(
    slot: SlotType,
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

    today     = date.today()
    date_str  = today.isoformat()
    token     = generate_token(current_user.id, slot.value, date_str)

    # check already scanned
    existing = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date    == today,
        Attendance.slot    == slot
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already scanned for this slot")

    # generate QR image
    qr_data = f"{current_user.id}:{slot.value}:{date_str}:{token}"
    img     = qrcode.make(qr_data)
    buf     = io.BytesIO()
    img.save(buf, format="PNG")
    b64     = base64.b64encode(buf.getvalue()).decode()

    return {
        "qr_base64": b64,
        "token":     token,
        "slot":      slot.value,
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
        slot     = parts[1]
        date_str = parts[2]
        token    = parts[3]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid QR data")

    # verify token
    expected = generate_token(user_id, slot, date_str)
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid QR token")

    # check date
    if date_str != date.today().isoformat():
        raise HTTPException(status_code=400, detail="QR expired — wrong date")

    # check already scanned
    existing = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date    == date.today(),
        Attendance.slot    == slot
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already scanned")

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