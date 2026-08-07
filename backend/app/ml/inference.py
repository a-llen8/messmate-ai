"""
MessMate — ML inference layer.

Loads the trained churn / headcount joblib artifacts and scores LIVE database
state (not the synthetic training set). This did not exist before the Ops
Agent — scripts/train_churn_model.py and scripts/train_headcount_model.py
only ever trained and saved models; nothing served predictions.

Feature engineering here is deliberately DUPLICATED from the training
scripts rather than imported, matching the existing project convention
(see build_exam_windows, copy-pasted across generate_synthetic_data.py /
train_churn_model.py / train_headcount_model.py with a "must stay
identical to that source" comment). Backend code shouldn't import from
scripts/, so the same rule applies here: if you change feature engineering
in the training scripts, mirror the change here or the model will be
scored on a different feature distribution than it was trained on.

KNOWN LIMITATION — exam periods: is_exam_period / exam_proximity are
computed with the same build_exam_windows() used by
scripts/generate_synthetic_data.py, anchored to the synthetic data's own
generation window (today - MONTHS*30 days at generation time). That window
is fixed and in the past relative to "today" at inference time, so for any
real calendar date past the synthetic set's end, these will evaluate to
0 / not-in-exam-period. This is fine for the current demo (all data is
synthetic) but will need a real academic-calendar source before this means
anything for genuinely upcoming dates.

Requires: pandas, numpy, scikit-learn, xgboost, joblib (added to
backend/requirements.txt — these were previously only used by the
scripts/ venv, not the backend app).
"""

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sqlalchemy import text

from app.core.database import engine

MODELS_DIR = Path(__file__).parent / "models"

MONTHS = 18  # must match scripts/generate_synthetic_data.py
BUFFER_DAYS = 7

PLAN_SLOTS = {
    "full": ["breakfast", "lunch", "dinner"],
    "breakfast_only": ["breakfast"],
    "lunch_only": ["lunch"],
    "dinner_only": ["dinner"],
    "breakfast_lunch": ["breakfast", "lunch"],
    "breakfast_dinner": ["breakfast", "dinner"],
    "lunch_dinner": ["lunch", "dinner"],
}

WEEKLY_MEALS = {
    "full": 21,
    "breakfast_lunch": 14,
    "breakfast_dinner": 14,
    "lunch_dinner": 14,
    "breakfast_only": 7,
    "lunch_only": 7,
    "dinner_only": 7,
}

HISTORY_LOOKBACK_DAYS = 90  # trailing window pulled for rolling features; comfortably > 30d windows


# ── Shared: exam window logic (ported, see module docstring) ────────────
def _build_exam_windows(start, total_days, months=MONTHS):
    windows = []
    num_exam_periods = max(2, months // 4)
    spacing = total_days // (num_exam_periods + 1)
    for i in range(1, num_exam_periods + 1):
        w_start = start + timedelta(days=spacing * i)
        w_end = w_start + timedelta(days=10)
        windows.append((w_start, w_end))
    return windows


def _in_any_window(d, windows):
    return any(w_start <= d <= w_end for w_start, w_end in windows)


def _exam_proximity_score(d, windows, buffer_days=BUFFER_DAYS):
    best = 0.0
    for w_start, w_end in windows:
        if w_start <= d <= w_end:
            return 1.0
        dist = (w_start - d).days if d < w_start else (d - w_end).days
        best = max(best, max(0.0, 1 - dist / buffer_days))
    return best


def _safe_bound(value, fallback: pd.Timestamp) -> pd.Timestamp:
    """pd.Timestamp(None) is NaT, and Python's min()/max() give undefined
    results when comparing NaT against a real Timestamp (NaT's comparison
    operators all return False, so min/max silently pick whichever operand
    happens to come first — not necessarily the "right" one, and it can
    smuggle a NaT through to pd.date_range(), which then raises).

    subscriptions.start_date / end_date are both nullable (see
    app/models/models.py) — an open-ended subscription can have
    end_date = NULL. Use `fallback` (the window's own natural bound —
    today, or history_start) for a missing value instead of guessing."""
    ts = pd.Timestamp(value)
    return fallback if pd.isna(ts) else ts


def _exam_windows_for(all_subs_start_dates: pd.Series, total_days_hint: int):
    """Anchor exam windows the same way training did: earliest subscription
    start_date seen, spanning MONTHS*30 days from there (or the observed
    range if shorter)."""
    starts = all_subs_start_dates.dropna()
    if starts.empty:
        return []
    anchor = pd.Timestamp(starts.min())
    total_days = max(total_days_hint, MONTHS * 30)
    return _build_exam_windows(anchor, total_days)


# ── Model loading (cached — joblib load is not free, and this runs once
#    per agent tool call, not per row) ───────────────────────────────────
@lru_cache(maxsize=1)
def _load_churn_model():
    model = joblib.load(MODELS_DIR / "churn_model.joblib")
    feature_cols = joblib.load(MODELS_DIR / "churn_model_features.joblib")
    threshold = joblib.load(MODELS_DIR / "churn_model_threshold.joblib")
    return model, feature_cols, threshold


@lru_cache(maxsize=1)
def _load_headcount_model():
    model = joblib.load(MODELS_DIR / "headcount_model.joblib")
    feature_cols = joblib.load(MODELS_DIR / "headcount_model_features.joblib")
    return model, feature_cols


# ── Churn: at-risk student lookup ────────────────────────────────────────
def get_at_risk_students(top_n: int = 15) -> list[dict]:
    """
    Score every currently-active subscriber as of today and return those
    at/above the tuned churn threshold, highest risk first.

    NOTE: unlike the training script, this does NOT filter to synth% emails
    — it scores whatever active subscriptions exist. On the current demo
    dataset that's still all synthetic users; this is the correct behavior
    for when real data exists too.
    """
    model, feature_cols, threshold = _load_churn_model()
    today = date.today()
    history_start = today - timedelta(days=HISTORY_LOOKBACK_DAYS)

    subs = pd.read_sql(text("""
        SELECT s.user_id, s.plan_type, s.status, s.start_date, s.end_date,
               u.name, u.email
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE s.status = 'active'
    """), engine)

    if subs.empty:
        return []

    all_starts = pd.read_sql(text("SELECT start_date FROM subscriptions"), engine)["start_date"]

    attendance = pd.read_sql(text("""
        SELECT a.user_id, a.date
        FROM attendance a
        WHERE a.date >= :history_start
    """), engine, params={"history_start": history_start})

    ratings = pd.read_sql(text("""
        SELECT r.user_id, m.date, r.score
        FROM ratings r
        JOIN menus m ON r.menu_id = m.id
        WHERE m.date >= :history_start
    """), engine, params={"history_start": history_start})

    complaints = pd.read_sql(text("""
        SELECT c.user_id, c.created_at::date AS date
        FROM complaints c
        WHERE c.created_at::date >= :history_start
    """), engine, params={"history_start": history_start})

    # Daily eligibility grid: from max(sub.start_date, history_start) to today
    rows = []
    skipped_no_start = 0
    for _, sub in subs.iterrows():
        if pd.isna(sub["start_date"]):
            skipped_no_start += 1
            continue
        grid_start = max(pd.Timestamp(sub["start_date"]), pd.Timestamp(history_start))
        grid_end = min(_safe_bound(sub["end_date"], pd.Timestamp(today)), pd.Timestamp(today))
        if grid_start > grid_end:
            continue
        n_slots = len(PLAN_SLOTS[sub["plan_type"]])
        for d in pd.date_range(grid_start, grid_end, freq="D"):
            rows.append((sub["user_id"], d, n_slots))

    if not rows:
        return []

    grid = pd.DataFrame(rows, columns=["user_id", "date", "eligible_slots"])

    attendance = attendance.copy()
    attendance["date"] = pd.to_datetime(attendance["date"])
    daily_attended = attendance.groupby(["user_id", "date"]).size().reset_index(name="attended_slots")

    daily = grid.merge(daily_attended, on=["user_id", "date"], how="left")
    daily["attended_slots"] = daily["attended_slots"].fillna(0)
    daily["daily_rate"] = (daily["attended_slots"] / daily["eligible_slots"]).clip(0, 1)
    daily = daily.sort_values(["user_id", "date"]).reset_index(drop=True)

    def add_rolling(df, col, window, out_col, agg="mean"):
        df[out_col] = (
            df.groupby("user_id")[col]
              .transform(lambda s: s.shift(1).rolling(window, min_periods=3).agg(agg))
        )
        return df

    daily = add_rolling(daily, "daily_rate", 7, "rate_7d")
    daily = add_rolling(daily, "daily_rate", 14, "rate_14d")
    daily = add_rolling(daily, "daily_rate", 30, "rate_30d")

    global_mean = daily["daily_rate"].mean()
    for c in ["rate_7d", "rate_14d", "rate_30d"]:
        daily[c] = daily[c].fillna(global_mean)
    daily["rate_trend"] = daily["rate_7d"] - daily["rate_30d"]

    ratings = ratings.copy()
    ratings["date"] = pd.to_datetime(ratings["date"])
    daily_rating = ratings.groupby(["user_id", "date"])["score"].mean().reset_index(name="daily_score")
    daily = daily.merge(daily_rating, on=["user_id", "date"], how="left")
    daily["daily_score"] = daily["daily_score"].fillna(0)
    daily = add_rolling(daily, "daily_score", 30, "avg_rating_30d")
    global_rating_mean = ratings["score"].mean() if not ratings.empty else 3.0
    daily["avg_rating_30d"] = daily["avg_rating_30d"].replace(0, np.nan).fillna(global_rating_mean)

    complaints = complaints.copy()
    complaints["date"] = pd.to_datetime(complaints["date"])
    daily_complaint = complaints.groupby(["user_id", "date"]).size().reset_index(name="complaint_flag")
    daily = daily.merge(daily_complaint, on=["user_id", "date"], how="left")
    daily["complaint_flag"] = daily["complaint_flag"].fillna(0)
    daily = add_rolling(daily, "complaint_flag", 30, "complaint_count_30d", agg="sum")
    daily["complaint_count_30d"] = daily["complaint_count_30d"].fillna(0)

    # Only need "today"'s row per user
    today_ts = pd.Timestamp(today)
    snapshot = daily[daily["date"] == today_ts].copy()
    if snapshot.empty:
        return []

    exam_windows = _exam_windows_for(all_starts, HISTORY_LOOKBACK_DAYS)
    snapshot["is_weekend"] = int(today.weekday() >= 5)
    snapshot["is_exam_period"] = int(_in_any_window(today_ts, exam_windows))

    subs_idx = subs.set_index("user_id")
    snapshot["plan_type"] = snapshot["user_id"].map(subs_idx["plan_type"])
    snapshot["start_date"] = snapshot["user_id"].map(subs_idx["start_date"])
    snapshot["tenure_days"] = snapshot.apply(
        lambda r: (today - pd.Timestamp(r["start_date"]).date()).days, axis=1
    )
    snapshot["weekly_meals"] = snapshot["plan_type"].map(WEEKLY_MEALS)

    X = snapshot.reindex(columns=feature_cols, fill_value=0)
    proba = model.predict_proba(X)[:, 1]
    snapshot["churn_proba"] = proba

    at_risk = snapshot[snapshot["churn_proba"] >= threshold].sort_values(
        "churn_proba", ascending=False
    ).head(top_n)

    results = []
    for _, row in at_risk.iterrows():
        info = subs_idx.loc[row["user_id"]]
        results.append({
            "user_id": int(row["user_id"]),
            "name": info["name"],
            "email": info["email"],
            "plan_type": info["plan_type"],
            "churn_probability": round(float(row["churn_proba"]), 4),
            "rate_trend_7v30": round(float(row["rate_trend"]), 4),
            "complaint_count_30d": int(row["complaint_count_30d"]),
            "avg_rating_30d": round(float(row["avg_rating_30d"]), 2),
            "tenure_days": int(row["tenure_days"]),
        })
    return results


# ── Headcount: tomorrow's demand forecast ───────────────────────────────
def get_headcount_forecast(target_date: date | None = None) -> list[dict]:
    """
    Predict headcount per meal slot for target_date (default: tomorrow —
    this is meant to inform prep for the next service, not today's, which
    is already underway).
    """
    model, feature_cols = _load_headcount_model()
    target_date = target_date or (date.today() + timedelta(days=1))
    history_start = target_date - timedelta(days=HISTORY_LOOKBACK_DAYS)

    subs = pd.read_sql(text("""
        SELECT user_id, plan_type, start_date, end_date
        FROM subscriptions
        WHERE status = 'active' OR end_date >= :history_start
    """), engine, params={"history_start": history_start})

    all_starts = pd.read_sql(text("SELECT start_date FROM subscriptions"), engine)["start_date"]

    attendance = pd.read_sql(text("""
        SELECT user_id, date, slot
        FROM attendance
        WHERE date >= :history_start AND date < :target_date
    """), engine, params={"history_start": history_start, "target_date": target_date})

    # Eligible-count grid across history_start..target_date (inclusive),
    # per (date, slot) — mirrors train_headcount_model.build_daily_headcount
    elig_rows = []
    for _, sub in subs.iterrows():
        if pd.isna(sub["start_date"]):
            continue
        grid_start = max(pd.Timestamp(sub["start_date"]), pd.Timestamp(history_start))
        grid_end = min(_safe_bound(sub["end_date"], pd.Timestamp(target_date)), pd.Timestamp(target_date))
        if grid_start > grid_end:
            continue
        for d in pd.date_range(grid_start, grid_end, freq="D"):
            for slot in PLAN_SLOTS[sub["plan_type"]]:
                elig_rows.append((d, slot))

    if not elig_rows:
        return []

    elig = pd.DataFrame(elig_rows, columns=["date", "slot"])
    eligible_counts = elig.groupby(["date", "slot"]).size().reset_index(name="eligible_students")

    attendance = attendance.copy()
    attendance["date"] = pd.to_datetime(attendance["date"])
    headcount = attendance.groupby(["date", "slot"]).size().reset_index(name="headcount")

    data = eligible_counts.merge(headcount, on=["date", "slot"], how="left")
    data["headcount"] = data["headcount"].fillna(0).astype(int)
    data = data[data["eligible_students"] > 0].reset_index(drop=True)
    data = data.sort_values(["slot", "date"]).reset_index(drop=True)

    def add_rolling(df, col, window, out_col):
        df[out_col] = (
            df.groupby("slot")[col]
              .transform(lambda s: s.shift(1).rolling(window, min_periods=3).mean())
        )
        return df

    data = add_rolling(data, "headcount", 7, "avg_headcount_7d")
    data = add_rolling(data, "headcount", 14, "avg_headcount_14d")
    data = add_rolling(data, "headcount", 28, "avg_headcount_28d")
    data["daily_rate"] = data["headcount"] / data["eligible_students"]
    data = add_rolling(data, "daily_rate", 14, "avg_rate_14d")

    global_rate_mean = data["daily_rate"].mean()
    for c in ["avg_headcount_7d", "avg_headcount_14d", "avg_headcount_28d"]:
        data[c] = data[c].fillna(data["headcount"].mean())
    data["avg_rate_14d"] = data["avg_rate_14d"].fillna(global_rate_mean)

    target_ts = pd.Timestamp(target_date)
    target_rows = data[data["date"] == target_ts].copy()
    if target_rows.empty:
        # No one eligible that day (shouldn't normally happen) — bail cleanly
        return []

    target_rows["day_of_week"] = target_ts.dayofweek
    target_rows["is_weekend"] = int(target_ts.dayofweek >= 5)
    target_rows["month"] = target_ts.month

    exam_windows = _exam_windows_for(all_starts, HISTORY_LOOKBACK_DAYS)
    target_rows["is_exam_period"] = int(_in_any_window(target_ts, exam_windows))
    target_rows["exam_proximity"] = _exam_proximity_score(target_ts, exam_windows)

    target_rows = pd.get_dummies(target_rows, columns=["slot"], prefix="slot")
    # Restore a 'slot' label column for the output (get_dummies consumed it)
    slot_names = []
    for _, row in target_rows.iterrows():
        for s in ["breakfast", "lunch", "dinner"]:
            if row.get(f"slot_{s}", False):
                slot_names.append(s)
                break
    target_rows = target_rows.reset_index(drop=True)
    target_rows["slot"] = slot_names

    X = target_rows.reindex(columns=feature_cols, fill_value=0)
    predictions = model.predict(X)

    results = []
    for i, row in target_rows.iterrows():
        results.append({
            "date": target_date.isoformat(),
            "slot": row["slot"],
            "predicted_headcount": round(float(predictions[i])),
            "eligible_students": int(row["eligible_students"]),
            "avg_headcount_7d": round(float(row["avg_headcount_7d"]), 1),
            "is_exam_period": bool(row["is_exam_period"]),
        })
    return sorted(results, key=lambda r: ["breakfast", "lunch", "dinner"].index(r["slot"]))