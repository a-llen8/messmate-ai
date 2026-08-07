from sqlalchemy import Column, Integer, String, Boolean, Float, Date, DateTime, Text, ForeignKey, Enum, Numeric, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum

class UserRole(str, enum.Enum):
    student = "student"
    caterer = "caterer"
    admin = "admin"

class SlotType(str, enum.Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"

class SubStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    cancelled = "cancelled"

class RequestType(str, enum.Enum):
    new = "new"
    cancel = "cancel"

class RequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

# ── Users ──────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    supabase_uid    = Column(String, unique=True, nullable=False)
    email           = Column(String, unique=True, nullable=False)
    name            = Column(String, nullable=False)
    phone           = Column(String)
    role            = Column(Enum(UserRole), default=UserRole.student)
    is_active       = Column(Boolean, default=True)
    is_super        = Column(Boolean, default=False)  # admin can invite others
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    subscription         = relationship("Subscription", back_populates="user", uselist=False)
    subscription_requests = relationship("SubscriptionRequest", back_populates="user")
    attendance           = relationship("Attendance", back_populates="user")
    ratings              = relationship("Rating", back_populates="user")

# ── Subscriptions ───────────────────────────────────────────
class Subscription(Base):
    __tablename__ = "subscriptions"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), unique=True)
    plan_type       = Column(String)  # full, lunch_only, etc
    status          = Column(Enum(SubStatus), default=SubStatus.active)
    start_date      = Column(Date)
    end_date        = Column(Date)
    price           = Column(Float)
    locked_price    = Column(Numeric(10, 2))  # price at subscription time, never changes
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user            = relationship("User", back_populates="subscription")

# ── Subscription Requests ────────────────────────────────────
class SubscriptionRequest(Base):
    __tablename__ = "subscription_requests"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"))
    type            = Column(Enum(RequestType), nullable=False)  # new or cancel
    plan_type       = Column(String)
    start_date      = Column(Date)
    end_date        = Column(Date)
    status          = Column(Enum(RequestStatus), default=RequestStatus.pending)
    reason          = Column(Text)  # for cancel requests
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user            = relationship("User", back_populates="subscription_requests")

# ── Menus ───────────────────────────────────────────────────
class Menu(Base):
    __tablename__ = "menus"

    id              = Column(Integer, primary_key=True, index=True)
    date            = Column(Date, nullable=False)
    slot            = Column(Enum(SlotType), nullable=False)
    items           = Column(Text)  # comma separated dish names
    nutrition_json  = Column(Text)  # JSON string
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    attendance      = relationship("Attendance", back_populates="menu")
    ratings         = relationship("Rating", back_populates="menu")

# ── Attendance ──────────────────────────────────────────────
class Attendance(Base):
    __tablename__ = "attendance"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"))
    menu_id         = Column(Integer, ForeignKey("menus.id"))
    date            = Column(Date, nullable=False)
    slot            = Column(Enum(SlotType), nullable=False)
    scanned_at      = Column(DateTime, server_default=func.now())
    qr_token        = Column(String)

    user            = relationship("User", back_populates="attendance")
    menu            = relationship("Menu", back_populates="attendance")

# ── Ratings ─────────────────────────────────────────────────
class Rating(Base):
    __tablename__ = "ratings"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"))
    menu_id         = Column(Integer, ForeignKey("menus.id"))
    score           = Column(Integer)  # 1-5
    comment         = Column(Text)
    sentiment       = Column(String)  # positive/negative/neutral
    created_at      = Column(DateTime, server_default=func.now())

    user            = relationship("User", back_populates="ratings")
    menu            = relationship("Menu", back_populates="ratings")

# ── Complaints ──────────────────────────────────────────────
class Complaint(Base):
    __tablename__ = "complaints"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"))
    text            = Column(Text, nullable=False)
    category        = Column(String)  # food_quality, hygiene, etc
    status          = Column(String, default="open")  # open, resolved
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ── Mess Info ───────────────────────────────────────────────
class MessInfo(Base):
    __tablename__ = "mess_info"

    id              = Column(Integer, primary_key=True, index=True)
    key             = Column(String, unique=True, nullable=False)
    value           = Column(Text)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ── Price Plans ─────────────────────────────────────────────
class PricePlan(Base):
    __tablename__ = "price_plans"

    id              = Column(Integer, primary_key=True, index=True)
    plan_type       = Column(String, unique=True, nullable=False)
    monthly_price   = Column(Numeric(10, 2), nullable=False)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ── Caterer Ops Agent ───────────────────────────────────────────
# Scope addition on top of the SRS-locked 9-table schema (MDSS582-4) —
# documented here as an explicit addition rather than folded into an
# existing table, since agent runs/actions/traces have a different
# lifecycle and access pattern (append-only, agent-written) from the
# core operational tables above.

class AgentRunStatus(str, enum.Enum):
    completed = "completed"    # model produced a validated submit_decision
    incomplete = "incomplete"  # hit MAX_ROUNDS without finalizing
    error = "error"            # API/network failure ended the run early

class ActionApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id                = Column(Integer, primary_key=True, index=True)
    run_date          = Column(Date, nullable=False, index=True)
    status            = Column(Enum(AgentRunStatus), nullable=False)
    summary           = Column(Text)  # dashboard header text, null if run didn't complete
    tools_consulted   = Column(Text)  # JSON list, e.g. '["get_churn_risk", "get_headcount_forecast"]'
    error             = Column(Text)  # populated for incomplete/error runs
    created_at        = Column(DateTime, server_default=func.now())

    actions           = relationship("AgentAction", back_populates="run", cascade="all, delete-orphan")
    traces            = relationship("AgentTrace", back_populates="run", cascade="all, delete-orphan")

class AgentAction(Base):
    __tablename__ = "agent_actions"

    id                = Column(Integer, primary_key=True, index=True)
    run_id            = Column(Integer, ForeignKey("agent_runs.id"), nullable=False, index=True)
    category          = Column(String, nullable=False)   # churn_retention | headcount_prep | complaint_followup | general
    priority          = Column(String, nullable=False)   # high | medium | low
    summary           = Column(Text, nullable=False)
    reasoning         = Column(Text, nullable=False)
    drafted_message   = Column(Text)
    related_user_id   = Column(Integer, ForeignKey("users.id"))
    related_date      = Column(Date)
    approval_status   = Column(Enum(ActionApprovalStatus), default=ActionApprovalStatus.pending, nullable=False)
    created_at        = Column(DateTime, server_default=func.now())
    updated_at        = Column(DateTime, server_default=func.now(), onupdate=func.now())

    run               = relationship("AgentRun", back_populates="actions")

class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id                = Column(Integer, primary_key=True, index=True)
    run_id            = Column(Integer, ForeignKey("agent_runs.id"), nullable=False, index=True)
    round_num         = Column(Integer, nullable=False)
    event_type        = Column(String, nullable=False)   # model_response | tool_call | tool_result | error
    detail            = Column(Text, nullable=False)      # JSON blob, shape varies by event_type
    created_at        = Column(DateTime, nullable=False)

    run               = relationship("AgentRun", back_populates="traces")

    __table_args__ = (
        CheckConstraint("round_num >= 1", name="ck_agent_traces_round_positive"),
    )