from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import json
from app.core.database import get_db
from app.api.deps import get_current_user, get_caterer
from app.models.models import (
    User, Menu, Subscription, SubscriptionRequest,
    Complaint, Attendance, MessInfo, SlotType,
    SubStatus, RequestStatus, RequestType, PricePlan, Rating,
    AgentRun, AgentAction, ActionApprovalStatus
)
from app.agents.tools import TOOL_CADENCE

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
    pending_agent_actions = db.query(AgentAction).filter(
        AgentAction.approval_status == ActionApprovalStatus.pending
    ).count()

    return {
        "total_students":         total_students,
        "active_subs":            active_subs,
        "today_attendance":       today_attendance,
        "open_complaints":        open_complaints,
        "pending_requests":       pending_requests,
        "pending_agent_actions":  pending_agent_actions,
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

# ── Price Plans ───────────────────────────────────────────────
class PricePlanUpdate(BaseModel):
    plan_type: str
    monthly_price: float

@router.post("/price-plans")
def set_price_plan(
    payload: PricePlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    plan = db.query(PricePlan).filter(PricePlan.plan_type == payload.plan_type).first()
    if plan:
        plan.monthly_price = payload.monthly_price
    else:
        plan = PricePlan(plan_type=payload.plan_type, monthly_price=payload.monthly_price)
        db.add(plan)
    db.commit()
    return {"message": f"Price for '{payload.plan_type}' set to ₹{payload.monthly_price}"}

@router.get("/price-plans")
def get_price_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    plans = db.query(PricePlan).all()
    return [{"plan_type": p.plan_type, "monthly_price": str(p.monthly_price)} for p in plans]

# ── Subscriptions ─────────────────────────────────────────────
class ApproveRequest(BaseModel):
    locked_price: Optional[float] = None

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
            "id":         r.id,
            "user_id":    r.user_id,
            "type":       r.type,
            "plan_type":  r.plan_type,
            "start_date": r.start_date,
            "end_date":   r.end_date,
            "created_at": r.created_at,
        }
        for r in requests
    ]

@router.post("/subscriptions/requests/{request_id}/approve")
def approve_request(
    request_id: int,
    payload: ApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    req = db.query(SubscriptionRequest).filter(SubscriptionRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    req.status = RequestStatus.approved

    if req.type == RequestType.new:
        price = payload.locked_price
        if price is None:
            plan = db.query(PricePlan).filter(PricePlan.plan_type == req.plan_type).first()
            if not plan:
                raise HTTPException(status_code=400, detail="No price plan set — enter locked_price manually")
            days = (req.end_date - req.start_date).days + 1
            price = round(float(plan.monthly_price) / 30 * days, 2)

        existing_sub = db.query(Subscription).filter(
            Subscription.user_id == req.user_id
        ).first()

        if existing_sub:
            existing_sub.plan_type    = req.plan_type
            existing_sub.status       = SubStatus.active
            existing_sub.start_date   = req.start_date
            existing_sub.end_date     = req.end_date
            existing_sub.locked_price = price
        else:
            sub = Subscription(
                user_id      = req.user_id,
                plan_type    = req.plan_type,
                status       = SubStatus.active,
                start_date   = req.start_date,
                end_date     = req.end_date,
                locked_price = price,
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

@router.get("/ratings")
def get_ratings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    menus = db.query(Menu).order_by(Menu.date.desc()).limit(30).all()
    result = []
    for m in menus:
        ratings = db.query(Rating).filter(Rating.menu_id == m.id).all()
        if not ratings:
            continue
        scores = [r.score for r in ratings]
        result.append({
            "menu_id":      m.id,
            "date":         m.date,
            "slot":         m.slot,
            "items":        m.items,
            "avg_score":    round(sum(scores) / len(scores), 2),
            "count":        len(scores),
            "comments":     [r.comment for r in ratings if r.comment],
        })
    return result

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

# ── Ops Agent recommendations ────────────────────────────────
# What the Caterer Ops Agent drafted (see app/agents/ops_agent.py) and is
# waiting on a human for. Nothing here was sent or executed automatically —
# every row starts approval_status="pending" and stays that way until a
# caterer approves, edits, or rejects it below.
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

@router.get("/agent-actions")
def get_agent_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    actions = db.query(AgentAction).filter(
        AgentAction.approval_status == ActionApprovalStatus.pending
    ).all()
    # priority is a plain string column ("high"/"medium"/"low"), not a DB
    # enum with defined ordering, so sort in Python rather than SQL —
    # alphabetical would wrongly put "low" before "medium".
    actions.sort(key=lambda a: (PRIORITY_ORDER.get(a.priority, 99), a.created_at))
    return [
        {
            "id":              a.id,
            "run_id":          a.run_id,
            "category":        a.category,
            "priority":        a.priority,
            "summary":         a.summary,
            "reasoning":       a.reasoning,
            "drafted_message": a.drafted_message,
            "related_user_id": a.related_user_id,
            "related_date":    a.related_date,
            "created_at":      a.created_at,
        }
        for a in actions
    ]

@router.post("/agent-actions/{action_id}/approve")
def approve_agent_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    action = db.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.approval_status != ActionApprovalStatus.pending:
        raise HTTPException(status_code=400, detail=f"Action already {action.approval_status.value}")

    action.approval_status = ActionApprovalStatus.approved
    db.commit()
    return {"message": f"Action {action_id} approved"}

class EditAgentAction(BaseModel):
    drafted_message: str

@router.post("/agent-actions/{action_id}/edit")
def edit_agent_action(
    action_id: int,
    payload: EditAgentAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    action = db.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.approval_status != ActionApprovalStatus.pending:
        raise HTTPException(status_code=400, detail=f"Action already {action.approval_status.value}")
    if not payload.drafted_message.strip():
        raise HTTPException(status_code=400, detail="drafted_message cannot be empty")

    # Only drafted_message is ever editable — summary/reasoning stay exactly
    # as the model produced them, since they're the audit trail of what the
    # agent actually found, not caterer-facing copy.
    action.drafted_message = payload.drafted_message.strip()
    action.approval_status = ActionApprovalStatus.edited
    db.commit()
    return {"message": f"Action {action_id} edited and approved"}

@router.post("/agent-actions/{action_id}/reject")
def reject_agent_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    action = db.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.approval_status != ActionApprovalStatus.pending:
        raise HTTPException(status_code=400, detail=f"Action already {action.approval_status.value}")

    action.approval_status = ActionApprovalStatus.rejected
    db.commit()
    return {"message": f"Action {action_id} rejected"}

@router.get("/agent-runs/health")
def get_agent_run_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_caterer)
):
    """Latest run per cadence (daily/weekly/monthly), inferred from each
    run's tools_consulted via tools.py's TOOL_CADENCE. agent_runs has no
    run_mode column — none needed, see ops_agent.py's execute_and_save()
    docstring and tools_consulted's own comment in models.py."""
    recent_runs = db.query(AgentRun).order_by(AgentRun.created_at.desc()).limit(30).all()

    latest_by_mode = {}
    for run in recent_runs:
        if len(latest_by_mode) == 3:
            break
        try:
            tools = json.loads(run.tools_consulted) if run.tools_consulted else []
        except (json.JSONDecodeError, TypeError):
            continue
        if not tools:
            continue
        mode = TOOL_CADENCE.get(tools[0])
        if mode and mode not in latest_by_mode:
            latest_by_mode[mode] = {
                "run_id":     run.id,
                "status":     run.status.value,
                "created_at": run.created_at,
                "error":      run.error,
            }

    return {
        "daily":   latest_by_mode.get("daily"),
        "weekly":  latest_by_mode.get("weekly"),
        "monthly": latest_by_mode.get("monthly"),
    }