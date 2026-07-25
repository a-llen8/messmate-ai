from sqlalchemy import Column, Integer, String, Boolean, Float, Date, DateTime, Text, ForeignKey, Enum, Numeric, UniqueConstraint
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

    __table_args__ = (
        UniqueConstraint(
            "user_id", "type",
            name="idx_one_pending_new"
        ),
    )

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