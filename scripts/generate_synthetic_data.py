"""
MessMate — Synthetic Data Generator (Week 5)

Generates 18 months of realistic-ish attendance / rating / complaint history
for a set of synthetic students, layered on top of your real schema.

WHAT IT CREATES
  - N synthetic students (default 200), each with an active Subscription
    on a random plan_type (weighted toward common plans)
  - Menus for every day x 3 slots across the date range, cycling through
    a dish list that includes a few intentionally "unpopular" dishes
  - Attendance rows, respecting each student's plan_type eligibility,
    with baked-in patterns:
      * per-student baseline regularity (some students are reliable,
        some are not)
      * weekend attendance dip
      * exam-week attendance dip (several windows across the 18 months)
      * slight per-slot popularity difference (breakfast < lunch/dinner)
  - Ratings for a portion of attendances, scored lower for the seeded
    "unpopular" dishes, with a derived sentiment label
  - Complaints for a fraction of low ratings

IDEMPOTENT: re-running this deletes any previously generated synthetic
rows first (identified by the synth% email pattern) before regenerating,
so it's safe to tune parameters and re-run without piling up duplicates
or touching your real accounts.

HOW TO RUN
    cd backend
    venv\\Scripts\\activate
    python ..\\scripts\\generate_synthetic_data.py

Adjust NUM_STUDENTS / MONTHS below before running if you want a
different size dataset.
"""

import sys
import os
import random
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.database import SessionLocal, engine
from app.models.models import (
    User, UserRole, Subscription, SubStatus,
    SubscriptionRequest, RequestType, RequestStatus,
    Menu, SlotType, Attendance, Rating, Complaint,
)

# ── Config ──────────────────────────────────────────────────────
NUM_STUDENTS = 200
MONTHS       = 18
SEED         = 42

# ── Churn simulation ──────────────────────────────────────────
# A subset of students cancel their subscription partway through. Attendance
# visibly declines in the weeks leading up to cancellation (not a random
# on/off switch) so a churn model actually has a learnable signal, not noise.
CHURN_RATE          = 0.22   # fraction of students who churn at some point
MIN_TENURE_DAYS     = 90     # no one churns in their first 3 months (needs history)
DECAY_WINDOW_DAYS   = 45     # attendance decays over this many days before cancellation
DECAY_FLOOR         = 0.15   # attendance probability multiplier at the moment of cancellation

CHURN_REASONS = [
    "Moving off campus",
    "Switching to home-cooked meals",
    "Budget constraints",
    "Quality of food not meeting expectations",
    "Graduating / leaving college",
    "Health / dietary reasons",
    "Prefer eating out",
]

PLAN_WEIGHTS = {
    "full":             0.35,
    "lunch_dinner":     0.20,
    "breakfast_lunch":  0.10,
    "breakfast_dinner": 0.10,
    "lunch_only":       0.10,
    "dinner_only":      0.10,
    "breakfast_only":   0.05,
}

PLAN_SLOTS = {
    "full":             {"breakfast", "lunch", "dinner"},
    "breakfast_only":   {"breakfast"},
    "lunch_only":       {"lunch"},
    "dinner_only":      {"dinner"},
    "breakfast_lunch":  {"breakfast", "lunch"},
    "breakfast_dinner": {"breakfast", "dinner"},
    "lunch_dinner":     {"lunch", "dinner"},
}

DISH_POOL = {
    "breakfast": ["Poha", "Idli Sambar", "Aloo Paratha", "Upma", "Bread Omelette", "Chana Masala"],
    "lunch":     ["Rice Dal Sabzi", "Rajma Chawal", "Curd Rice", "Veg Biryani", "Roti Sabzi Dal", "Khichdi"],
    "dinner":    ["Chapati Curry", "Fried Rice Manchurian", "Pulao Raita", "Dal Roti Sabzi", "Noodles", "Paneer Butter Masala"],
}

# intentionally unpopular dishes — will get systematically lower ratings
UNPOPULAR_DISHES = {"Khichdi", "Bread Omelette", "Curd Rice"}

SLOT_BASE_ATTENDANCE = {
    "breakfast": 0.55,
    "lunch":     0.75,
    "dinner":    0.70,
}

COMPLAINT_CATEGORIES = ["food_quality", "hygiene", "quantity", "service"]
COMPLAINT_TEMPLATES = [
    "The {slot} today was undercooked and not up to the usual standard.",
    "Found the {slot} portion size too small for the price.",
    "The serving area for {slot} was not clean today.",
    "Had to wait a long time to be served during {slot}.",
    "The {slot} tasted stale, please check the ingredients.",
]

def load_complaint_pool():
    import json
    pool_path = os.path.join(os.path.dirname(__file__), "data", "complaint_pool.json")
    if not os.path.exists(pool_path):
        print("WARNING: complaint_pool.json not found — run generate_complaint_pool.py first.")
        print("Falling back to the 15 fixed COMPLAINT_TEMPLATES strings.")
        return {
            slot: [t.format(slot=slot) for t in COMPLAINT_TEMPLATES]
            for slot in ["breakfast", "lunch", "dinner"]
        }
    with open(pool_path, "r", encoding="utf-8") as f:
        return json.load(f)

COMPLAINT_POOL = load_complaint_pool()

random.seed(SEED)


def daterange(start, end):
    days = (end - start).days + 1
    for i in range(days):
        yield start + timedelta(days=i)


def build_exam_windows(start, total_days):
    """A few 10-day exam windows spread roughly evenly across the range."""
    windows = []
    num_exam_periods = max(2, MONTHS // 4)
    spacing = total_days // (num_exam_periods + 1)
    for i in range(1, num_exam_periods + 1):
        w_start = start + timedelta(days=spacing * i)
        w_end = w_start + timedelta(days=10)
        windows.append((w_start, w_end))
    return windows


def in_any_window(d, windows):
    return any(w_start <= d <= w_end for w_start, w_end in windows)


def weighted_choice(weights_dict):
    keys = list(weights_dict.keys())
    weights = list(weights_dict.values())
    return random.choices(keys, weights=weights, k=1)[0]


def main():
    db = SessionLocal()

    print("Removing any previously generated synthetic rows...")
    old_students = db.query(User).filter(User.email.like("synth%@messmate.local")).all()
    old_ids = [s.id for s in old_students]
    if old_ids:
        db.query(Complaint).filter(Complaint.user_id.in_(old_ids)).delete(synchronize_session=False)
        db.query(Rating).filter(Rating.user_id.in_(old_ids)).delete(synchronize_session=False)
        db.query(Attendance).filter(Attendance.user_id.in_(old_ids)).delete(synchronize_session=False)
        db.query(SubscriptionRequest).filter(SubscriptionRequest.user_id.in_(old_ids)).delete(synchronize_session=False)
        db.query(Subscription).filter(Subscription.user_id.in_(old_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(old_ids)).delete(synchronize_session=False)
        db.commit()
        print(f"  removed {len(old_ids)} old synthetic students and their data")

    end_date = date.today()
    start_date = end_date - timedelta(days=MONTHS * 30)
    total_days = (end_date - start_date).days + 1
    exam_windows = build_exam_windows(start_date, total_days)

    print(f"Date range: {start_date} to {end_date} ({total_days} days)")
    print(f"Exam windows: {exam_windows}")

    # ── Students + Subscriptions ──────────────────────────────
    print(f"Creating {NUM_STUDENTS} synthetic students...")
    students = []
    for i in range(1, NUM_STUDENTS + 1):
        email = f"synth{i:04d}@messmate.local"
        u = User(
            supabase_uid = str(uuid.uuid4()),
            email        = email,
            name         = f"Synthetic Student {i:04d}",
            phone        = f"9{random.randint(100000000, 999999999)}",
            role         = UserRole.student,
            is_active    = True,
        )
        db.add(u)
        students.append(u)
    db.flush()  # get IDs without committing yet

    student_plans = {}
    student_reliability = {}  # per-student baseline attendance propensity
    churn_date_map = {}       # user_id -> churn date, only present for churners
    earliest_churn = start_date + timedelta(days=MIN_TENURE_DAYS)

    for u in students:
        plan = weighted_choice(PLAN_WEIGHTS)
        student_plans[u.id] = plan
        student_reliability[u.id] = random.betavariate(6, 2)  # skewed toward reliable, some low outliers

        is_churner = random.random() < CHURN_RATE
        if is_churner and earliest_churn < end_date:
            span_days = (end_date - earliest_churn).days
            churn_date = earliest_churn + timedelta(days=random.randint(0, span_days))
            churn_date_map[u.id] = churn_date

            sub = Subscription(
                user_id      = u.id,
                plan_type    = plan,
                status       = SubStatus.cancelled,
                start_date   = start_date,
                end_date     = churn_date,
                locked_price = round(random.uniform(1500, 6000), 2),
            )
            db.add(sub)
            db.flush()

            req = SubscriptionRequest(
                user_id    = u.id,
                type       = RequestType.cancel,
                plan_type  = plan,
                start_date = start_date,
                end_date   = churn_date,
                status     = RequestStatus.approved,
                reason     = random.choice(CHURN_REASONS),
            )
            db.add(req)
        else:
            sub = Subscription(
                user_id      = u.id,
                plan_type    = plan,
                status       = SubStatus.active,
                start_date   = start_date,
                end_date     = None,  # open-ended - ongoing until cancelled
                locked_price = round(random.uniform(1500, 6000), 2),
            )
            db.add(sub)
    db.commit()
    print(f"  created {len(students)} students with subscriptions")
    print(f"  {len(churn_date_map)} students churn during the period "
          f"({len(churn_date_map)/len(students):.1%})")

    # ── Menus ──────────────────────────────────────────────────
    print("Generating menus...")
    menu_lookup = {}  # (date, slot) -> Menu
    dish_cursor = {"breakfast": 0, "lunch": 0, "dinner": 0}
    for d in daterange(start_date, end_date):
        for slot_name in ["breakfast", "lunch", "dinner"]:
            dishes = DISH_POOL[slot_name]
            item = dishes[dish_cursor[slot_name] % len(dishes)]
            dish_cursor[slot_name] += 1
            m = Menu(
                date  = d,
                slot  = SlotType(slot_name),
                items = item,
            )
            db.add(m)
            menu_lookup[(d, slot_name)] = m
    db.commit()
    print(f"  created {len(menu_lookup)} menu rows")

    # need real IDs for Attendance/Rating FK — refresh menu objects
    for key, m in menu_lookup.items():
        db.refresh(m)

    # ── Attendance + Ratings + Complaints ────────────────────
    print("Generating attendance, ratings, complaints (this is the big one)...")
    attendance_batch = []
    rating_batch = []
    complaint_batch = []

    for d in daterange(start_date, end_date):
        is_weekend = d.weekday() >= 5
        is_exam = in_any_window(d, exam_windows)

        for u in students:
            churn_date = churn_date_map.get(u.id)
            if churn_date is not None and d > churn_date:
                continue  # subscription already cancelled — no longer eligible for mess

            plan = student_plans[u.id]
            reliability = student_reliability[u.id]
            allowed_slots = PLAN_SLOTS[plan]

            decay_mult = 1.0
            if churn_date is not None:
                decay_start = churn_date - timedelta(days=DECAY_WINDOW_DAYS)
                if d >= decay_start:
                    decay_frac = (d - decay_start).days / DECAY_WINDOW_DAYS
                    decay_mult = 1 - (1 - DECAY_FLOOR) * min(1.0, decay_frac)

            for slot_name in allowed_slots:
                menu = menu_lookup[(d, slot_name)]

                p = reliability * SLOT_BASE_ATTENDANCE[slot_name] * decay_mult
                if is_weekend:
                    p *= 0.7
                if is_exam:
                    p *= 0.5

                if random.random() < p:
                    attendance_batch.append({
                        "user_id":  u.id,
                        "menu_id":  menu.id,
                        "date":     d,
                        "slot":     SlotType(slot_name),
                        "qr_token": "synthetic",
                    })

                    # ~40% of attendances also leave a rating
                    if random.random() < 0.4:
                        is_unpopular = menu.items in UNPOPULAR_DISHES
                        if is_unpopular:
                            score = max(1, min(5, round(random.gauss(2.2, 0.8))))
                        else:
                            score = max(1, min(5, round(random.gauss(4.0, 0.7))))

                        sentiment = "positive" if score >= 4 else ("negative" if score <= 2 else "neutral")

                        rating_batch.append({
                            "user_id":   u.id,
                            "menu_id":   menu.id,
                            "score":     score,
                            "comment":   None,
                            "sentiment": sentiment,
                        })

                        # low ratings sometimes turn into a complaint
                        if score <= 2 and random.random() < 0.3:
                            complaint_batch.append({
                                "user_id":  u.id,
                                "text":     random.choice(COMPLAINT_POOL[slot_name]),
                                "category": random.choice(COMPLAINT_CATEGORIES),
                                "status":   random.choice(["open", "resolved", "resolved", "resolved"]),
                            })

        # flush in batches per day-ish chunk to keep memory sane
        if len(attendance_batch) > 20000:
            db.bulk_insert_mappings(Attendance, attendance_batch)
            db.commit()
            attendance_batch = []
        if len(rating_batch) > 20000:
            db.bulk_insert_mappings(Rating, rating_batch)
            db.commit()
            rating_batch = []
        if len(complaint_batch) > 20000:
            db.bulk_insert_mappings(Complaint, complaint_batch)
            db.commit()
            complaint_batch = []

    # flush remainder
    if attendance_batch:
        db.bulk_insert_mappings(Attendance, attendance_batch)
    if rating_batch:
        db.bulk_insert_mappings(Rating, rating_batch)
    if complaint_batch:
        db.bulk_insert_mappings(Complaint, complaint_batch)
    db.commit()

    total_attendance = db.query(Attendance).join(User).filter(User.email.like("synth%")).count()
    total_ratings = db.query(Rating).join(User).filter(User.email.like("synth%")).count()
    total_complaints = db.query(Complaint).join(User).filter(User.email.like("synth%")).count()

    print("\nDone.")
    print(f"  Students:    {NUM_STUDENTS}")
    print(f"  Menus:       {len(menu_lookup)}")
    print(f"  Attendance:  {total_attendance}")
    print(f"  Ratings:     {total_ratings}")
    print(f"  Complaints:  {total_complaints}")

    db.close()


if __name__ == "__main__":
    main()