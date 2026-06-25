# MESSMATE — COMPLETE PROJECT PLAN v2.0
### Hostel Mess Management System with Agentic AI
> All drawbacks identified and fixed. Every aspect covered.

---

## TABLE OF CONTENTS
1. Overview
2. Tech Stack
3. Database Schema
4. System Users & Auth
5. Student Module
6. Caterer Module
7. QR Attendance System
8. AI Agents (all 5)
9. Nutrition System
10. Notification System
11. Payment System
12. Security
13. Data Simulation
14. Model Retraining Pipeline
15. Build Order (10 Weeks)
16. Deployment
17. Future Extensions

---

## 1. OVERVIEW

MessMate is a hostel mess management system with 5 background AI agents.
Covers subscriptions, menus, complaints, attendance, and nutrition.
Two users: Student and Caterer. Role-based routing from shared login.

---

## 2. TECH STACK

| Layer       | Technology                                                                 |
|-------------|---------------------------------------------------------------------------|
| Backend     | FastAPI + PostgreSQL + SQLAlchemy + Alembic                               |
| Task Queue  | Celery + Redis (NOT APScheduler — survives restarts)                      |
| Frontend    | React + TailwindCSS + Recharts + React Router + PWA                       |
| AI/LLM      | Google Gemini 2.0 Flash API (FREE — 1500 req/day)                         |
| ML          | XGBoost (Agent 2) + LightGBM (Agent 4) + sentence-transformers + BERTopic |
| Auth        | Supabase (JWT, signup, login, email reset, email notifications)            |
| Nutrition   | IFCT local DB + Edamam API fallback (free tier: 10K calls/month)          |
| Security    | slowapi (rate limiting) + HMAC (QR tokens) + bcrypt                       |
| Infra       | Docker Compose (5 containers)                                             |
| Hardware    | 1 phone/tablet with camera at counter (caterer) — no extra hardware       |

### Why Gemini over Claude API
- Gemini 2.0 Flash: 1,500 requests/day FREE, no card needed
- MessMate needs ~35 calls/month total (Agent 1 + Agent 5)
- Sufficient quality for structured JSON output tasks
- Get key at: aistudio.google.com → free

### Why Celery over APScheduler
- APScheduler state lost on crash/restart → missed jobs silently
- Celery + Redis → job state persists → reliable scheduling

---

## 3. DATABASE SCHEMA

### Core Tables

```sql
-- Users (students + caterers)
users (
  id              SERIAL PRIMARY KEY,
  name            VARCHAR(100) NOT NULL,
  email           VARCHAR(255) UNIQUE NOT NULL,
  role            ENUM('student', 'caterer') NOT NULL,
  college         VARCHAR(100),
  course          VARCHAR(100),
  year            INTEGER,
  supabase_uid    VARCHAR(255) UNIQUE,   -- links to Supabase auth
  created_at      TIMESTAMP DEFAULT NOW()
)

-- Caterer accounts (supports multiple caterer seats)
caterer_accounts (
  id              SERIAL PRIMARY KEY,
  user_id         INTEGER REFERENCES users(id),
  is_super        BOOLEAN DEFAULT FALSE,  -- admin can invite others
  created_at      TIMESTAMP DEFAULT NOW()
)

-- Mess info
mess_info (
  id              SERIAL PRIMARY KEY,
  description     TEXT,
  timings         JSONB,   -- {"breakfast":"7-9am","lunch":"12-2pm","dinner":"7-9pm"}
  guidelines      TEXT,
  monthly_price   DECIMAL(10,2),
  updated_at      TIMESTAMP DEFAULT NOW()
)

-- Slot cutoff times (caterer can adjust)
slot_cutoffs (
  id              SERIAL PRIMARY KEY,
  slot            ENUM('breakfast','lunch','dinner'),
  cutoff_time     TIME,    -- auto-absent fires at this time
  updated_at      TIMESTAMP DEFAULT NOW()
)

-- Meal plans
meal_plans (
  id              SERIAL PRIMARY KEY,
  name            VARCHAR(100),
  slots           JSONB,   -- {"breakfast":true,"lunch":true,"dinner":true}
  price           DECIMAL(10,2),
  is_active       BOOLEAN DEFAULT TRUE
)

-- Subscription requests (new + cancel, unified queue)
subscription_requests (
  id              SERIAL PRIMARY KEY,
  student_id      INTEGER REFERENCES users(id),
  plan_id         INTEGER REFERENCES meal_plans(id),
  type            ENUM('new','cancel') NOT NULL,
  status          ENUM('pending','approved','rejected') DEFAULT 'pending',
  created_at      TIMESTAMP DEFAULT NOW(),
  resolved_at     TIMESTAMP,
  resolved_by     INTEGER REFERENCES users(id)
)

-- Prevent duplicate pending requests at DB level
CREATE UNIQUE INDEX idx_one_pending_new
  ON subscription_requests(student_id)
  WHERE type = 'new' AND status = 'pending';

-- Subscriptions
subscriptions (
  id                  SERIAL PRIMARY KEY,
  student_id          INTEGER REFERENCES users(id),
  plan_id             INTEGER REFERENCES meal_plans(id),
  start_date          DATE NOT NULL,
  end_date            DATE NOT NULL,
  status              ENUM('active','expired','cancelled') DEFAULT 'active',
  locked_price        DECIMAL(10,2),       -- price at time of subscription (not affected by future price changes)
  payment_status      ENUM('unpaid','paid','partial') DEFAULT 'unpaid',
  payment_note        TEXT,                -- "Cash collected 3 July"
  payment_marked_at   TIMESTAMP,
  payment_marked_by   INTEGER REFERENCES users(id),
  churn_label_source  ENUM('rule','real') DEFAULT 'rule',
  created_at          TIMESTAMP DEFAULT NOW()
)

-- Menus
menus (
  id              SERIAL PRIMARY KEY,
  date            DATE UNIQUE NOT NULL,
  published_at    TIMESTAMP,
  published_by    INTEGER REFERENCES users(id)
)

-- Menu items (dish-level rows — not a single text field)
menu_items (
  id              SERIAL PRIMARY KEY,
  menu_id         INTEGER REFERENCES menus(id),
  slot            ENUM('breakfast','lunch','dinner'),
  dish_id         INTEGER REFERENCES dishes(id),   -- NULL if is_custom
  dish_name_free  VARCHAR(200),                     -- filled if dish not in DB
  is_custom       BOOLEAN DEFAULT FALSE
)

-- Dish master (IFCT-linked)
dishes (
  id              SERIAL PRIMARY KEY,
  name            VARCHAR(200) NOT NULL,
  ifct_code       VARCHAR(20),            -- maps to IFCT database
  aliases         TEXT[],                 -- {"Idly","Idlee","Idli"} — seed manually
  calories        DECIMAL(8,2),
  protein         DECIMAL(8,2),
  carbs           DECIMAL(8,2),
  fat             DECIMAL(8,2),
  iron            DECIMAL(8,2),
  calcium         DECIMAL(8,2),
  fibre           DECIMAL(8,2),
  is_custom       BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMP DEFAULT NOW()
)

-- Complaints
complaints (
  id              SERIAL PRIMARY KEY,
  student_id      INTEGER REFERENCES users(id),
  title           VARCHAR(200),
  description     TEXT,
  category        ENUM('food_quality','quantity','hygiene','service','other'),
  severity        ENUM('normal','urgent') DEFAULT 'normal',   -- NEW
  status          ENUM('open','resolved') DEFAULT 'open',
  created_at      TIMESTAMP DEFAULT NOW(),
  resolved_at     TIMESTAMP,
  resolved_by     INTEGER REFERENCES users(id)
)

-- Special dates (exam/holiday — used by Agent 2)
special_dates (
  id              SERIAL PRIMARY KEY,
  date            DATE NOT NULL,
  type            ENUM('exam','holiday','festival'),
  note            TEXT,
  created_at      TIMESTAMP DEFAULT NOW()
)
```

### AI/ML Tables

```sql
-- Meal attendance
meal_attendance (
  id              SERIAL PRIMARY KEY,
  student_id      INTEGER REFERENCES users(id),   -- NULL if aggregate row
  date            DATE NOT NULL,
  slot            ENUM('breakfast','lunch','dinner'),
  attended        BOOLEAN,
  aggregate_count INTEGER,                          -- used during caterer headcount phase
  marked_at       TIMESTAMP,
  source          ENUM('qr_scan','name_search','auto_absent','simulated','caterer_aggregate'),
  created_at      TIMESTAMP DEFAULT NOW()
)

-- Meal ratings (shown after slot cutoff passes)
meal_ratings (
  id              SERIAL PRIMARY KEY,
  student_id      INTEGER REFERENCES users(id),
  date            DATE NOT NULL,
  slot            ENUM('breakfast','lunch','dinner'),
  rating          INTEGER CHECK (rating BETWEEN 1 AND 5),
  created_at      TIMESTAMP DEFAULT NOW()
)

-- Agent outputs (versioned)
agent_insights (
  id              SERIAL PRIMARY KEY,
  agent_name      VARCHAR(50),
  model_version   VARCHAR(50),        -- "xgb_v1", "rule_based", "gemini_flash"
  llm_provider    VARCHAR(20),        -- "gemini", "local", null
  run_date        DATE,
  output_json     JSONB,
  created_at      TIMESTAMP DEFAULT NOW()
)

-- ML model registry
model_registry (
  id              SERIAL PRIMARY KEY,
  agent_name      VARCHAR(50),
  version         VARCHAR(50),
  auc_score       DECIMAL(6,4),
  train_rows      INTEGER,
  is_active       BOOLEAN DEFAULT FALSE,
  trained_at      TIMESTAMP DEFAULT NOW()
)

-- Student QR tokens
student_qrs (
  id              SERIAL PRIMARY KEY,
  student_id      INTEGER REFERENCES users(id) UNIQUE,
  qr_token        VARCHAR(64) NOT NULL,   -- HMAC-signed, not raw student_id
  qr_path         VARCHAR(255),           -- path to stored PNG
  semester        VARCHAR(20),            -- "2025-odd" — rotate per semester
  generated_at    TIMESTAMP DEFAULT NOW()
)
```

---

## 4. SYSTEM USERS & AUTH

### Auth Flow
```
Supabase handles:
  - Student self-registration
  - JWT token on login
  - Password reset via email
  - Email notifications (subscription approval, QR delivery)

Caterer accounts:
  - Admin created at deploy time via admin script
  - Admin can invite 1-2 more caterer seats from caterer dashboard
  - Invitation sent via Supabase admin email → temp password + reset link
  - Never plain-text credentials
```

### Route Protection
```
All routes protected → redirect to /login if no JWT
Role check on every protected route:
  /student/* → role must be 'student'
  /caterer/* → role must be 'caterer'
```

---

## 5. STUDENT MODULE

### 5.1 Register + Login
- Register: name, email, password, college, course, year
- Shared login page (caterer + student) — role-based redirect on success
- JWT stored in httpOnly cookie (not localStorage — XSS protection)

### 5.2 Student Dashboard
- Shows mess description, timings, guidelines from mess_info
- Shows current subscription status badge
- Shows today's menu (if published)
- Shows AI nutrition score for today (Agent 5 output)

### 5.3 My Profile
- View personal + academic details
- Edit profile
- View personal QR code (generated on subscription approval)
- Download QR as PNG button

### 5.4 Choose Meal Plan
- View available meal plans with slot breakdown + pricing
- locked_price shown (price at subscription time — won't change)
- Select plan + desired start date → submit subscription_request
- Guard: cannot submit if pending/active subscription exists (DB-level + frontend)

### 5.5 My Subscription
- Current status: pending / active / expired / cancelled
- Subscription history
- Delete pending request
- Request cancellation for active plan (creates cancel request in subscription_requests)
- Payment status visible (paid / unpaid / partial)

### 5.6 Today's Menu
- Breakfast / Lunch / Dinner items for today
- Updates live when caterer publishes
- Per-slot nutrition score from Agent 5 (0-100, with traffic light color)
- Meal rating widget (1-5 stars) — visible only after slot cutoff time passes
- Rating stored in meal_ratings

### 5.7 Submit Complaint
- Fields: title, category (dropdown), severity (normal/urgent), description
- Submitted complaint visible in complaint history with status

---

## 6. CATERER MODULE

### 6.1 Caterer Dashboard
- Real-time headcount: active subscriptions per slot for today
- Agent 2 prediction widget: "Tomorrow — B: 45 | L: 120 | D: 80 (ML)" or "(Rule-based)" depending on mode
- Agent 5 weekly nutrition gap alert: "Low protein this week — add dal/eggs"
- High-churn student count badge
- Pending subscription requests count
- Urgent complaints badge (real-time — not waiting for weekly cluster)

### 6.2 Update Today's Menu
- Search from predefined Indian dish list (with fuzzy match for aliases)
- Free text fallback if dish not found → stored as is_custom = TRUE
- Publish → instantly visible to students
- Every publish stored in menus + menu_items tables
- Agent 1 suggestion panel: "This week's AI suggestion" — editable table pre-filled from Agent 1 JSON

### 6.3 Manage Subscriptions
- Tab 1 — Pending Requests: approve / reject each new request
  - On approve:
    1. Create subscription with locked_price = current monthly_price
    2. Auto-generate HMAC-signed QR for student
    3. Email student with QR attached + approval notice
- Tab 2 — Active Subscribers: list with churn badge 🔴🟡🟢 (Agent 4)
  - Hover/click badge → SHAP explanation: top 2 reasons in plain English
- Tab 3 — Cancellation Requests: approve or reject
- Mark Payment: per-student payment_status toggle + note field

### 6.4 View Complaints
- All complaints listed, filterable by category / severity / status / date
- Mark as resolved
- Agent 3 panel: weekly clustered summary + downloadable PDF report
- Urgent complaints shown at top with 🚨 badge (not waiting for weekly cluster)

### 6.5 Update Mess Info
- Edit description, timings, guidelines, monthly_price
- Price change: only affects NEW subscriptions. Existing subscriptions keep locked_price.
- Warning shown: "X students on old price. Migrate manually?"

### 6.6 Special Dates Manager
- Calendar UI: mark exam / holiday / festival dates
- Used by Agent 2 as feature input
- Date picker + type dropdown + optional note

### 6.7 Attendance — Caterer View
- Tab: Breakfast / Lunch / Dinner
- Shows all students subscribed to that slot today
- Live: marked present (green) / unmarked (grey) as students scan QR
- At cutoff time: remaining unmarked auto-marked absent
- Caterer can manually override individual attendance
- Caterer headcount form (fallback when no QR available): 3 number inputs → saves aggregate row

### 6.8 Slot Cutoff Settings
- Adjust cutoff times per slot (defaults: Breakfast 9:30, Lunch 14:30, Dinner 21:00)
- Celery Beat picks up changes immediately

---

## 7. QR ATTENDANCE SYSTEM

### Security Design
QR does NOT encode raw student_id (guessable).
Uses HMAC signature — unforgeable without SECRET_KEY.

```python
import hmac, hashlib, os, qrcode, io

SECRET_KEY = os.environ["QR_SECRET"]   # 32-byte random string, in .env
SEMESTER   = os.environ["QR_SEMESTER"] # e.g. "2025-odd" — rotate per semester

def generate_qr_token(student_id: int) -> str:
    payload = f"{student_id}:{SEMESTER}"
    token = hmac.new(
        SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:16]
    return f"messmate:{student_id}:{token}"

def verify_qr_token(qr_payload: str) -> int | None:
    """Returns student_id if valid, None if tampered/invalid."""
    parts = qr_payload.split(":")
    if len(parts) != 3 or parts[0] != "messmate":
        return None
    student_id, token = int(parts[1]), parts[2]
    expected = generate_qr_token(student_id).split(":")[-1]
    if hmac.compare_digest(token, expected):  # timing-safe compare
        return student_id
    return None

def generate_qr_image(student_id: int) -> bytes:
    token = generate_qr_token(student_id)
    qr = qrcode.make(token)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    return buf.getvalue()
```

### QR Lifecycle
```
Subscription approved
  → generate_qr_image(student_id)
  → save PNG to /media/qr/{student_id}.png
  → insert into student_qrs table
  → email PNG to student

Student at counter
  → shows QR on phone (from profile page)
  → caterer scans via browser camera (PWA — no app install)
  → backend verify_qr_token()
  → mark attended in meal_attendance

Semester rotation
  → change QR_SEMESTER env var
  → run: python manage.py regenerate_all_qrs
  → batch email new QRs to all active students
```

### Fallback: Name Search
If student forgot phone:
```
Caterer: Attendance → Lunch → Search student name
→ Type name → autocomplete from today's subscribed list
→ Tap name → mark present
→ source = 'name_search'
```

### Auto-Absent Celery Job
```python
@celery_app.task
def auto_mark_absent(slot: str):
    """Runs at slot cutoff time. Marks all unscanned students absent."""
    today = date.today()
    subscribed = get_subscribed_students_for_slot(today, slot)
    already_marked = get_marked_students(today, slot)
    absent_ids = set(subscribed) - set(already_marked)

    for student_id in absent_ids:
        db.add(MealAttendance(
            student_id=student_id,
            date=today,
            slot=slot,
            attended=False,
            source='auto_absent'
        ))
    db.commit()

# Schedule in Celery Beat (reads from slot_cutoffs table)
# Breakfast: 09:30, Lunch: 14:30, Dinner: 21:00
```

---

## 8. AI AGENTS

### LLM Setup (Gemini — Free)
```python
import google.generativeai as genai
import os

genai.configure(api_key=os.environ["GEMINI_API_KEY"])  # from aistudio.google.com
model = genai.GenerativeModel("gemini-2.0-flash")

def call_gemini(prompt: str, expect_json: bool = True) -> dict | str:
    response = model.generate_content(prompt)
    text = response.text.strip()
    if expect_json:
        import json
        # strip markdown fences if present
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    return text
```

---

### AGENT 1 — Menu Planner

| Property | Value |
|----------|-------|
| Trigger  | Weekly — Sunday 10 PM |
| Input    | menu_history (last 4 weeks) + meal_ratings + meal_attendance |
| Model    | Gemini 2.0 Flash |
| Output   | Suggested next week's menu (JSON) |
| Plugs in | Caterer > Update Menu > Suggestion panel |

```python
@celery_app.task
def run_agent1_menu_planner():
    history = get_last_4_weeks_menu()     # from menu_items
    ratings = get_avg_ratings_per_dish()   # from meal_ratings
    attendance = get_slot_attendance()     # from meal_attendance

    prompt = f"""
You are a hostel mess menu planner. Based on:
- Recent menus: {history}
- Dish ratings (1-5): {ratings}
- Attendance by slot: {attendance}

Suggest next week's menu. Rules:
- Avoid dishes rated below 2.5 two weeks in a row
- Rotate proteins (dal/egg/paneer/chicken)
- High-rated dishes can repeat fortnightly

Return ONLY this JSON, no other text:
{{
  "week_start": "YYYY-MM-DD",
  "days": [
    {{
      "date": "YYYY-MM-DD",
      "day": "Monday",
      "breakfast": ["dish1", "dish2"],
      "lunch": ["dish1", "dish2", "dish3"],
      "dinner": ["dish1", "dish2"]
    }}
  ]
}}
"""
    result = call_gemini(prompt)
    db.add(AgentInsight(
        agent_name="menu_planner",
        model_version="gemini-2.0-flash",
        llm_provider="gemini",
        run_date=date.today(),
        output_json=result
    ))
    db.commit()
    # Caterer sees this in Update Menu page — can edit before publishing
```

---

### AGENT 2 — Waste Reduction (Attendance Predictor)

| Property | Value |
|----------|-------|
| Trigger  | Daily — 9 PM (for next day) |
| Input    | meal_attendance + special_dates + day_of_week |
| Model    | XGBoost (cold-start: rule-based until 200 real rows) |
| Output   | Predicted headcount per slot for tomorrow |
| Plugs in | Caterer Dashboard > Prediction widget |

```python
@celery_app.task
def run_agent2_waste_reduction():
    tomorrow = date.today() + timedelta(days=1)
    real_rows = get_real_attendance_count()  # source != 'simulated'

    predictions = {}
    for slot in ['breakfast', 'lunch', 'dinner']:
        if real_rows < 200:
            pred, mode = rule_based_predict(tomorrow, slot)
        else:
            pred, mode = xgboost_predict(tomorrow, slot)
        predictions[slot] = {"count": pred, "mode": mode}

    # Alert if prediction is significantly lower than average
    avg = get_avg_attendance()
    for slot, data in predictions.items():
        if data["count"] < avg[slot] * 0.70:
            send_caterer_email(
                subject=f"⚠️ Low attendance predicted for {slot} tomorrow",
                body=f"Predicted: {data['count']} vs avg: {avg[slot]}. Consider reducing prep."
            )

    db.add(AgentInsight(
        agent_name="waste_reduction",
        model_version=get_active_model_version("agent2"),
        run_date=tomorrow,
        output_json=predictions
    ))
    db.commit()

def rule_based_predict(date, slot) -> tuple[int, str]:
    """Used until 200 real rows collected."""
    active = get_active_subscriptions_for_slot(slot)
    base_rates = {"breakfast": 0.65, "lunch": 0.80, "dinner": 0.75}
    dow_factors = {6: 0.85, 0: 0.90}       # Sunday, Monday lower
    rate = base_rates[slot] * dow_factors.get(date.weekday(), 1.0)
    if is_exam_day(date):    rate *= 0.70
    if is_holiday(date):     rate *= 0.50
    if is_festival_day(date): rate *= 0.60
    return int(active * rate), "rule_based"

def xgboost_predict(date, slot) -> tuple[int, str]:
    """Used after 200+ real rows."""
    features = build_features(date, slot)   # lag features, rolling avg, day-of-week, special date flags
    model = load_active_model("agent2")
    pred = model.predict([features])[0]
    return int(pred), "ml_model"
```

**Features for XGBoost:**
```
- day_of_week (0-6)
- is_exam (0/1)
- is_holiday (0/1)
- is_festival (0/1)
- rolling_7d_avg_attendance (per slot)
- rolling_30d_avg_attendance (per slot)
- lag_1d_attendance, lag_7d_attendance
- active_subscriptions_count
- month (1-12)
```

---

### AGENT 3 — Complaint Analyzer

| Property | Value |
|----------|-------|
| Trigger  | Weekly — Monday 6 AM + urgent complaints real-time |
| Input    | complaints table (last 7 days) |
| Model    | BERTopic (≥20 complaints) or KeyBERT (< 20 complaints) |
| Output   | Clustered categories + recurring issues + PDF report |
| Plugs in | Caterer > View Complaints > Summary panel |

```python
@celery_app.task
def run_agent3_complaint_analyzer():
    complaints = get_complaints_last_7_days()

    if len(complaints) == 0:
        return

    if len(complaints) < 20:
        # Sparse fallback: KeyBERT keyword extraction + rule buckets
        result = analyze_sparse(complaints)
    else:
        # BERTopic clustering
        result = analyze_dense(complaints)

    generate_pdf_report(result)           # saved to /media/reports/
    db.add(AgentInsight(
        agent_name="complaint_analyzer",
        model_version="bertopic_v1" if len(complaints) >= 20 else "kebert_sparse",
        run_date=date.today(),
        output_json=result
    ))
    db.commit()

def analyze_sparse(complaints):
    """KeyBERT + rule-based category buckets for < 20 complaints."""
    from keybert import KeyBERT
    kw_model = KeyBERT()
    categories = {"food_quality": 0, "quantity": 0, "hygiene": 0, "service": 0, "other": 0}
    for c in complaints:
        categories[c.category] += 1
        keywords = kw_model.extract_keywords(c.description, top_n=3)
    return {
        "mode": "keyword_extraction",
        "category_counts": categories,
        "top_keywords": keywords,
        "complaint_count": len(complaints)
    }

# Real-time urgent alert (fires on complaint submission, NOT weekly)
def handle_urgent_complaint(complaint):
    send_caterer_email(
        subject="🚨 Urgent Complaint - MessMate",
        body=f"Category: {complaint.category}\n"
             f"Student: {complaint.student.name}\n"
             f"Description: {complaint.description}\n"
             f"Submitted: {complaint.created_at}"
    )
```

---

### AGENT 4 — Churn Predictor

| Property | Value |
|----------|-------|
| Trigger  | Weekly — Sunday 11 PM |
| Input    | complaints + meal_attendance + meal_ratings + subscription age |
| Model    | LightGBM (cold-start: rule-based, saves pseudo-labels) |
| Output   | Risk score per student: High/Medium/Low + top 2 SHAP reasons |
| Plugs in | Caterer > Manage Subscriptions > risk badge per student |

```python
@celery_app.task
def run_agent4_churn_predictor():
    students = get_active_students()
    real_churn_events = count_real_cancellations()

    for student in students:
        features = build_churn_features(student)  # see below

        if real_churn_events < 50:
            # Rule-based cold start
            risk, reason = rule_based_churn(features)
            label_source = "rule"
        else:
            # LightGBM
            model = load_active_model("agent4")
            risk = predict_churn(model, features)
            reason = get_shap_explanation(model, features, student)
            label_source = "real"

        update_student_churn_risk(student.id, risk, reason, label_source)

def build_churn_features(student):
    return {
        "meal_skip_rate_30d":      get_skip_rate(student.id, days=30),
        "avg_rating_30d":          get_avg_rating(student.id, days=30),
        "complaint_count_30d":     get_complaint_count(student.id, days=30),
        "subscription_age_days":   get_subscription_age(student.id),
        "days_since_last_meal":    get_days_since_last_meal(student.id),
        "rating_trend":            get_rating_trend(student.id),    # slope of last 4 weeks
        "has_cancel_request":      has_pending_cancel(student.id),
    }

def rule_based_churn(features) -> tuple[str, list[str]]:
    score = 0
    if features["meal_skip_rate_30d"] > 0.50: score += 3
    if features["avg_rating_30d"] < 2.5:       score += 2
    if features["complaint_count_30d"] >= 3:    score += 2
    if features["days_since_last_meal"] > 7:    score += 2
    if features["has_cancel_request"]:          score += 5

    risk = "High" if score >= 6 else "Medium" if score >= 3 else "Low"
    return risk, get_top2_reasons(features)

# SHAP explanation → human-readable strings
FEATURE_TEMPLATES = {
    "meal_skip_rate_30d":    "Skipped {val}% of meals in last 30 days",
    "avg_rating_30d":        "Average meal rating {val}/5 this month",
    "complaint_count_30d":   "Filed {val} complaints in last 30 days",
    "days_since_last_meal":  "No meal recorded in last {val} days",
    "subscription_age_days": "Only subscribed for {val} days",
}

def get_shap_explanation(model, features, student):
    import shap
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values([list(features.values())])[0]
    feat_names = list(features.keys())
    top2 = sorted(zip(feat_names, shap_values), key=lambda x: abs(x[1]), reverse=True)[:2]
    return [
        FEATURE_TEMPLATES.get(feat, feat).format(val=round(features[feat], 1))
        for feat, _ in top2
    ]
```

---

### AGENT 5 — Nutritional Balance

| Property | Value |
|----------|-------|
| Trigger  | Daily — after caterer publishes menu |
| Input    | Today's menu_items → IFCT lookup → Edamam fallback |
| Model    | Gemini 2.0 Flash (for gap analysis) |
| Output   | Nutrition score per slot + weekly gap report |
| Plugs in | Student > Today's Menu (score) + Caterer Dashboard (weekly alert) |

```python
@celery_app.task
def run_agent5_nutrition(menu_id: int):
    """Triggered when caterer publishes menu."""
    items = get_menu_items(menu_id)
    nutrition_data = {}

    for item in items:
        if item.is_custom:
            # Try Edamam
            nutrition = fetch_edamam(item.dish_name_free)
        else:
            # IFCT local DB lookup with fuzzy match
            nutrition = lookup_ifct(item.dish_id)
            if not nutrition:
                nutrition = fetch_edamam(item.dish.name)

        if nutrition:
            nutrition_data[item.dish_name_free or item.dish.name] = nutrition

    # Score each slot
    slot_scores = compute_slot_scores(nutrition_data)

    # Weekly gap analysis via Gemini
    weekly_history = get_weekly_nutrition_totals()  # last 7 days
    prompt = f"""
Analyze this hostel mess weekly nutrition data:
{weekly_history}

Daily targets: 2000+ cal, 50g+ protein, 25g+ fibre, 900mg+ calcium

Return ONLY this JSON:
{{
  "weekly_score": 0-100,
  "gaps": ["low protein (avg 38g/day)", "low iron"],
  "suggestions": ["Add dal or eggs to Tuesday lunch", "Include leafy greens"]
}}
"""
    weekly_analysis = call_gemini(prompt)

    db.add(AgentInsight(
        agent_name="nutrition_balance",
        model_version="gemini-2.0-flash",
        llm_provider="gemini",
        run_date=date.today(),
        output_json={"slot_scores": slot_scores, "weekly": weekly_analysis}
    ))
    db.commit()

    # Alert caterer if gaps found
    if weekly_analysis["gaps"]:
        send_caterer_email(
            subject="🥗 Weekly Nutrition Alert - MessMate",
            body=f"Gaps: {', '.join(weekly_analysis['gaps'])}\n"
                 f"Suggestions: {', '.join(weekly_analysis['suggestions'])}"
        )
```

**IFCT Dish Lookup (fuzzy match):**
```python
from rapidfuzz import process, fuzz

def lookup_ifct(dish_id: int = None, dish_name: str = None):
    if dish_id:
        return db.query(Dish).filter(Dish.id == dish_id).first()

    # Fuzzy match on name + aliases
    all_dishes = db.query(Dish).all()
    all_names = []
    name_to_dish = {}
    for d in all_dishes:
        all_names.append(d.name)
        name_to_dish[d.name] = d
        for alias in (d.aliases or []):
            all_names.append(alias)
            name_to_dish[alias] = d

    match, score, _ = process.extractOne(dish_name, all_names, scorer=fuzz.WRatio)
    if score >= 85:
        return name_to_dish[match]

    # Below threshold → Edamam fallback
    return None

def fetch_edamam(dish_name: str):
    """Edamam Food Database API — free tier: 10K calls/month."""
    import requests
    resp = requests.get(
        "https://api.edamam.com/api/food-database/v2/parser",
        params={
            "app_id":  os.environ["EDAMAM_APP_ID"],
            "app_key": os.environ["EDAMAM_APP_KEY"],
            "ingr":    dish_name,
            "nutrition-type": "cooking"
        }
    )
    if resp.status_code == 200:
        food = resp.json()["hints"][0]["food"]["nutrients"]
        return {
            "calories": food.get("ENERC_KCAL", 0),
            "protein":  food.get("PROCNT", 0),
            "fat":      food.get("FAT", 0),
            "carbs":    food.get("CHOCDF", 0),
            "fibre":    food.get("FIBTG", 0),
        }
    return None
```

---

## 9. NUTRITION SYSTEM

### IFCT Database
- 528 Indian foods with full nutritional breakdown (NIN, Hyderabad)
- Seed into dishes table at launch
- Dish aliases manually seeded (50-100 common variants):
  ```
  Idli / Idly / Idlee
  Chapati / Chapathi / Roti / Phulka
  Sambar / Sambhar
  Rasam / Rasam / Rasa
  Poha / Pohay / Aval
  ... (full list: one-time task in Phase 1)
  ```

### Nutrition Scoring Formula
```python
def compute_slot_score(nutrients: dict) -> int:
    score = 100
    if nutrients["calories"] < 500:  score -= 20
    if nutrients["protein"] < 12:    score -= 20
    if nutrients["fibre"] < 5:       score -= 15
    if nutrients["iron"] < 3:        score -= 10
    if nutrients["calcium"] < 200:   score -= 10
    return max(0, score)

# Color coding in UI:
# 80-100 → green
# 60-79  → yellow
# <60    → red
```

---

## 10. NOTIFICATION SYSTEM

All via Supabase email (no extra infra). Events and triggers:

| Event | Recipient | Trigger |
|-------|-----------|---------|
| Subscription approved | Student | Caterer approves in UI |
| Subscription rejected | Student | Caterer rejects in UI |
| QR code delivery | Student | On subscription approval (PNG attached) |
| Complaint resolved | Student | Caterer marks resolved |
| Urgent complaint received | Caterer | Student submits severity=urgent |
| Low attendance prediction | Caterer | Agent 2: predicted < 70% of avg |
| Weekly nutrition gap | Caterer | Agent 5: gaps found |
| Subscription expiry warning | Student | 7 days before end_date |
| Subscription expired | Student | Day of expiry |

### Subscription Expiry Celery Job
```python
@celery_app.task
def check_subscription_expiry():
    """Runs daily at 00:01."""
    today = date.today()

    # 7-day warning
    expiring_soon = db.query(Subscription).filter(
        Subscription.end_date == today + timedelta(days=7),
        Subscription.status == 'active'
    ).all()
    for sub in expiring_soon:
        send_email(sub.student, "Subscription expiring in 7 days")

    # Auto-expire
    expired = db.query(Subscription).filter(
        Subscription.end_date < today,
        Subscription.status == 'active'
    ).all()
    for sub in expired:
        sub.status = 'expired'
        send_email(sub.student, "Subscription expired")
    db.commit()
```

---

## 11. PAYMENT SYSTEM

Offline only (MVP). No payment gateway.

### Flow
```
Student pays cash/UPI to caterer directly.
Caterer marks payment in system.
```

### Caterer Action
```
Manage Subscriptions → Active → [Student Row]
[Payment: Unpaid ▼]  →  Paid / Partial
[Note: Cash collected 3 July]
[Save]
```

### Fields in subscriptions table
```
payment_status      : unpaid / paid / partial
payment_note        : free text (optional)
payment_marked_at   : timestamp
payment_marked_by   : caterer user_id
```

### Razorpay (Phase 2 / SaaS path)
Not in MVP. Documented for future:
- Student pays online → webhook confirms → subscription activates auto
- Estimated: 3 days of work

---

## 12. SECURITY

### Rate Limiting
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/auth/login")
@limiter.limit("10/minute")
async def login(): ...

@app.post("/complaints")
@limiter.limit("5/minute")
async def submit_complaint(): ...

@app.post("/subscription-requests")
@limiter.limit("3/minute")
async def create_subscription_request(): ...
```

### QR Token Security
- HMAC-SHA256 signed with SECRET_KEY (never stored raw student_id alone)
- Rotated per semester (QR_SEMESTER env var)
- hmac.compare_digest() for timing-safe comparison (no timing attacks)

### Auth
- JWT stored in httpOnly cookie (not localStorage — XSS safe)
- Supabase handles token refresh
- Passwords: bcrypt via Supabase

### Database
- Unique index prevents duplicate pending requests (race condition fix)
- Parameterized queries via SQLAlchemy (no SQL injection)

### API
- CORS configured to frontend domain only
- No sensitive data in API responses (no password hashes, no QR tokens)

---

## 13. DATA SIMULATION

### What to Simulate
```
SIMULATE:
  meal_attendance  (18 months, per-student per-slot)
  meal_ratings     (18 months, per-student per-slot)
  menu_history     (via menus + menu_items tables)
  complaint history (with categories, no text — Agent 3 needs text, skip)
  special_dates    (seed exam calendar manually)

DO NOT SIMULATE:
  churn labels      (use rule-based pseudo-labels instead)
  complaint text    (KeyBERT/BERTopic needs real text)
  IFCT nutrition    (real data from IFCT database)
```

### Simulation Script
```python
import numpy as np
import pandas as pd
from faker import Faker
from datetime import date, timedelta

fake = Faker('en_IN')

STUDENTS = 100                          # simulate 100 students
SLOTS = ['breakfast', 'lunch', 'dinner']
START_DATE = date(2024, 1, 1)
END_DATE   = date(2025, 6, 30)          # 18 months

BASE_RATES = {
    "breakfast": 0.65,
    "lunch":     0.80,
    "dinner":    0.75
}

DOW_FACTORS = {
    6: 0.80,   # Sunday
    5: 0.85,   # Saturday
    0: 0.90    # Monday
}

EXAM_DATES = [...]  # manual seed

def simulate_attendance(student_id, date, slot):
    base = BASE_RATES[slot]
    base *= DOW_FACTORS.get(date.weekday(), 1.0)
    if date in EXAM_DATES:  base *= 0.70
    # Individual student variation: some students consistently skip breakfast
    student_factor = np.random.uniform(0.7, 1.0)  # fixed per student
    p = min(base * student_factor, 0.99)
    return bool(np.random.binomial(1, p))

def simulate_rating(student_id, attended, date, slot):
    if not attended:
        return None  # no rating if absent
    # Simulate gradual satisfaction drift
    base_rating = np.random.choice([3, 4, 5], p=[0.2, 0.5, 0.3])
    return base_rating

rows = []
for student_id in range(1, STUDENTS + 1):
    current = START_DATE
    while current <= END_DATE:
        for slot in SLOTS:
            attended = simulate_attendance(student_id, current, slot)
            rows.append({
                "student_id": student_id,
                "date":       current,
                "slot":       slot,
                "attended":   attended,
                "source":     "simulated",
                "marked_at":  None
            })
        current += timedelta(days=1)

df = pd.DataFrame(rows)
# Write to DB via SQLAlchemy bulk insert
```

### Train/Validation Split
```
Training  : Jan 2024 → Dec 2024 (12 months)
Validation: Jan 2025 → Jun 2025 (6 months)
```

### Retrain Trigger
Real data collected after launch. Retrain when real rows > 1000 (monthly check).

---

## 14. MODEL RETRAINING PIPELINE

```python
@celery_app.task
def monthly_retrain():
    """Runs 1st of every month at 2 AM."""

    for agent in ["agent2", "agent4"]:
        real_count = get_real_rows(agent)
        threshold  = {"agent2": 500, "agent4": 50}[agent]

        if real_count < threshold:
            log(f"{agent}: only {real_count} real rows. Skip retrain.")
            continue

        X, y = prepare_features(agent)
        new_model = train_model(agent, X, y)
        new_auc   = cross_validate(new_model, X, y)
        curr_auc  = get_active_model_auc(agent)

        if new_auc > curr_auc + 0.01:   # meaningful improvement threshold
            version = f"{agent}_v{timestamp()}"
            save_model(new_model, version)
            update_active_model(agent, version)
            db.add(ModelRegistry(
                agent_name=agent,
                version=version,
                auc_score=new_auc,
                train_rows=real_count,
                is_active=True
            ))
            log(f"{agent}: retrained. AUC {curr_auc:.4f} → {new_auc:.4f}")
        else:
            log(f"{agent}: no improvement. Keep current. ({new_auc:.4f} vs {curr_auc:.4f})")

        db.commit()
```

### Model Storage
```
/models/
  agent2_rule_based.pkl     ← always present as fallback
  agent2_xgb_v1.pkl
  agent2_xgb_v2.pkl         ← becomes active after retrain
  agent4_rule_based.pkl
  agent4_lgbm_v1.pkl
  active_models.json        ← {"agent2": "agent2_xgb_v2", "agent4": "rule_based"}
```

---

## 15. BUILD ORDER — 10 WEEKS

### Phase 1 — Week 1: Setup + Database + Auth
```
Tasks:
  ✓ Initialize FastAPI project with folder structure
  ✓ Docker Compose: FastAPI + PostgreSQL + Redis + Celery + Nginx
  ✓ SQLAlchemy models for ALL tables (full schema above)
  ✓ Alembic migrations
  ✓ Supabase project setup (auth, email)
  ✓ Environment variables: .env file
      GEMINI_API_KEY, QR_SECRET, QR_SEMESTER,
      EDAMAM_APP_ID, EDAMAM_APP_KEY, DATABASE_URL,
      SUPABASE_URL, SUPABASE_KEY
  ✓ Seed IFCT data into dishes table
  ✓ Seed dish aliases (50-100 variants — one-time task)
  ✓ Seed default slot cutoffs
  ✓ Seed default mess_info
  ✓ Create admin account via admin script
  ✓ Rate limiting setup (slowapi)
  ✓ CORS setup

Deliverable: Running FastAPI server with DB connected. Auth working.
```

### Phase 2 — Week 2: Backend APIs
```
Tasks:
  ✓ Auth endpoints: /register, /login, /logout, /reset-password
  ✓ Student endpoints:
      GET  /mess-info
      GET  /meal-plans
      POST /subscription-requests
      GET  /subscriptions/me
      DELETE /subscription-requests/{id}
      POST /subscription-requests/{id}/cancel
      GET  /menus/today
      POST /complaints
      GET  /complaints/me
      POST /meal-ratings
      GET  /qr/me  (returns QR PNG)
  ✓ Caterer endpoints:
      GET  /subscription-requests (pending queue)
      POST /subscription-requests/{id}/approve
      POST /subscription-requests/{id}/reject
      GET  /subscriptions (all active)
      PATCH /subscriptions/{id}/payment
      GET  /menus
      POST /menus  (publish menu)
      GET  /complaints (all)
      PATCH /complaints/{id}/resolve
      GET  /attendance/{slot}/today
      POST /attendance/aggregate  (caterer headcount fallback)
      POST /attendance/scan  (QR scan endpoint)
      PATCH /mess-info
      GET  /agent-insights/{agent_name}/latest
      POST /special-dates
      GET  /caterer-accounts  (admin only)
      POST /caterer-accounts/invite  (admin only)

  ✓ QR endpoints:
      GET  /qr/{student_id}  (caterer-side, returns PNG)
      POST /qr/verify  (receives QR payload, returns student info)

Deliverable: All APIs documented in Swagger at /docs. Postman tested.
```

### Phase 3 — Week 3: Frontend — Student Module
```
Tasks:
  ✓ React project setup + TailwindCSS + React Router
  ✓ PWA manifest + service worker (for camera access on mobile)
  ✓ Shared login page
  ✓ Student pages:
      /student/dashboard
      /student/profile  (+ QR display + download button)
      /student/meal-plans
      /student/subscription
      /student/menu  (+ nutrition score + rating widget)
      /student/complaints
  ✓ Route guards (redirect to /login if no JWT)
  ✓ API integration for all student endpoints

Deliverable: Full student flow working end-to-end.
```

### Phase 4 — Week 4: Frontend — Caterer Module + QR System
```
Tasks:
  ✓ Caterer pages:
      /caterer/dashboard  (prediction widget + alerts)
      /caterer/menu  (update + Agent 1 suggestion panel)
      /caterer/subscriptions  (tabs: pending / active / cancel)
      /caterer/complaints  (+ Agent 3 summary panel)
      /caterer/attendance  (QR scan + name search + live counter)
      /caterer/mess-info
      /caterer/special-dates
      /caterer/settings  (slot cutoffs)
  ✓ QR scanner component (browser camera via html5-qrcode library)
  ✓ Churn badge component (🔴🟡🟢 + hover tooltip with SHAP reasons)
  ✓ Payment mark component

Deliverable: Full caterer flow working end-to-end. QR scan tested on mobile.
```

### Phase 5 — Week 5: Data Simulation
```
Tasks:
  ✓ Write simulation script (meal_attendance 18 months)
  ✓ Write simulation script (meal_ratings 18 months)
  ✓ Write simulation script (menus + menu_items 18 months)
  ✓ Write simulation script (complaints — category only, no text)
  ✓ Validate output: distributions look realistic
      Check: avg attendance rate per slot per DOW
      Check: rating distribution (not all 5s)
      Check: complaint category balance
  ✓ Insert simulated data into DB
  ✓ Tag all rows with source='simulated'

Deliverable: 18 months simulated data in DB. Distributions validated.
```

### Phase 6 — Week 6: ML Model Training
```
Tasks:
  ✓ Agent 2 (XGBoost):
      Feature engineering script
      Train on 12 months, validate on 6
      Target AUC > 0.75
      Save model + log to model_registry
  ✓ Agent 4 (LightGBM):
      Build pseudo-labels from rule_based_churn()
      Feature engineering script
      Train on pseudo-labels
      Log churn_label_source = 'rule' for all
  ✓ Agent 3 (BERTopic):
      Test on simulated complaint categories
      Tune min_cluster_size for hostel scale
  ✓ Rule-based fallbacks:
      Verify rule_based_predict() output looks sensible
      Verify rule_based_churn() outputs balanced distribution

Deliverable: All models trained, saved to /models/. Baselines logged.
```

### Phase 7 — Week 7: Agents 3 + 2 + 1
```
Tasks:
  ✓ Celery Beat schedule setup
  ✓ Agent 3 implementation + test
      Run on simulated complaints
      Verify PDF report generates
      Test sparse fallback (< 20 complaints)
      Test urgent email fires correctly
  ✓ Agent 2 implementation + test
      Verify rule_based mode active (< 200 real rows)
      Verify prediction email fires when low
      Verify output renders in caterer dashboard
  ✓ Agent 1 implementation + test
      Test Gemini API call
      Verify JSON output parses correctly
      Verify suggestion panel renders in caterer menu page

Deliverable: Agents 1, 2, 3 running on schedule. Outputs visible in UI.
```

### Phase 8 — Week 8: Agents 4 + 5 + Retraining Pipeline
```
Tasks:
  ✓ Agent 4 implementation + test
      Verify churn badges render correctly
      Verify SHAP explanation strings render in tooltip
      Verify rule-based mode active
  ✓ Agent 5 implementation + test
      Test IFCT lookup (exact + fuzzy)
      Test Edamam fallback
      Test Gemini weekly gap analysis
      Verify nutrition score renders in student menu
      Verify weekly alert email fires
  ✓ Monthly retraining Celery task
      Dry run with simulated data
      Verify model_registry logging
      Verify champion/challenger swap logic

Deliverable: All 5 agents operational. Retraining pipeline tested.
```

### Phase 9 — Week 9: Integration Testing
```
Tasks:
  ✓ Full end-to-end flows:
      Student registers → subscription approved → QR generated → email received
      Student shows QR → caterer scans → attendance marked
      Cutoff time fires → auto-absent job runs → DB updated
      Caterer publishes menu → Agent 5 triggers → score visible to student
      Student rates meal → data feeds Agent 1 next week
      Student submits urgent complaint → caterer email fires immediately
      Agent outputs all render in UI (no blank panels)
  ✓ Seed fake agent_insights rows → verify all dashboard panels handle data
  ✓ Test rate limits (brute force login simulation)
  ✓ Test QR tamper (modify student_id in payload → should reject)
  ✓ Test subscription race condition (two simultaneous requests → one rejected)
  ✓ Test subscription expiry job

Deliverable: All flows verified. Bug list documented and fixed.
```

### Phase 10 — Week 10: Polish + Pilot Deploy
```
Tasks:
  ✓ Error handling: all API errors return structured JSON
  ✓ Loading states in all frontend components
  ✓ Empty state handling (no menu published yet, no complaints, etc.)
  ✓ Mobile responsiveness check
  ✓ PWA: camera works for QR scan on Android Chrome
  ✓ .env.production with real keys
  ✓ Deploy Docker Compose on VPS (DigitalOcean $6/mo droplet or college server)
  ✓ Domain + HTTPS (Let's Encrypt via Certbot)
  ✓ Pilot: 20-30 students + 1 caterer for 2 weeks
  ✓ Collect feedback, fix blockers

Deliverable: Live system. Pilot running.
```

---

## 16. DEPLOYMENT

### Docker Compose (Production)
```yaml
version: "3.9"
services:

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: messmate
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASS}
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

  api:
    build: ./backend
    env_file: .env
    depends_on: [db, redis]
    volumes:
      - ./media:/app/media      # QR PNGs, PDF reports
      - ./models:/app/models    # ML model files

  worker:
    build: ./backend
    command: celery -A app.celery worker --loglevel=info
    env_file: .env
    depends_on: [db, redis]
    volumes:
      - ./media:/app/media
      - ./models:/app/models

  beat:
    build: ./backend
    command: celery -A app.celery beat --loglevel=info
    env_file: .env
    depends_on: [db, redis]

  frontend:
    build: ./frontend
    command: nginx -g "daemon off;"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certbot:/etc/letsencrypt
    depends_on: [api, frontend]

volumes:
  pgdata:
```

### Minimum Hardware
```
VPS: 2 vCPU, 2GB RAM, 20GB SSD → DigitalOcean $12/mo (or college server)
Caterer device: 1 Android/iOS phone or tablet with Chrome browser
No other hardware needed
```

### Environment Variables
```bash
# .env (never commit to git)
DATABASE_URL=postgresql://user:pass@db:5432/messmate
REDIS_URL=redis://redis:6379/0
SUPABASE_URL=https://xyz.supabase.co
SUPABASE_KEY=your_service_key
GEMINI_API_KEY=your_gemini_key     # aistudio.google.com — free
EDAMAM_APP_ID=your_edamam_id      # edamam.com — free tier
EDAMAM_APP_KEY=your_edamam_key
QR_SECRET=32_random_chars_here    # openssl rand -hex 32
QR_SEMESTER=2025-odd              # rotate per semester
```

---

## 17. FUTURE EXTENSIONS

| Extension | Phase | Notes |
|-----------|-------|-------|
| Razorpay online payments | Phase 2 | 3 days. Auto-activate on payment |
| WhatsApp Business alerts | Phase 2 | Replace email for caterer |
| React Native mobile app | Phase 3 | Reuse all APIs |
| Multi-mess SaaS | Phase 4 | Add hostel_id to all tables |
| Agent 6 — Budget Optimizer | After inventory module added | Needs ingredient cost data |
| College chains (Manipal, VIT) | After SaaS | |

---

## OPEN CHECKLIST — BEFORE LAUNCH

- [ ] aistudio.google.com → get free Gemini API key
- [ ] edamam.com → register free tier (needs card but 10K calls/month free)
- [ ] Supabase project created + email SMTP configured
- [ ] Dish alias list manually seeded (50-100 variants)
- [ ] Special dates seeded (exam calendar from college)
- [ ] QR_SECRET generated (openssl rand -hex 32)
- [ ] QR_SEMESTER set for current term
- [ ] Admin account created via admin script
- [ ] Caterer notified of credentials via Supabase invite email
- [ ] Slot cutoffs set correctly (IST)
- [ ] Edamam fallback tested with 5 custom dishes
- [ ] All .env vars confirmed in production

---

*MessMate v2.0 — All drawbacks resolved. Build-ready.*
