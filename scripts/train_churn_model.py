"""
MessMate — Week 7: Churn Prediction Model (script version)

Clean, linear script version of notebooks/churn_model.ipynb, for use in
a retraining pipeline or by a backend service — no cells, no inline plots,
just train -> evaluate -> save.

Predicts: is THIS student at risk of cancelling their subscription within
the next 30 days, based on a snapshot of their behavior so far (rolling
attendance rate, trend, ratings, complaints, tenure). This is a genuinely
different problem from the Week 6 per-meal attendance model.

IMPORTANT: requires scripts/generate_synthetic_data.py to have been run
with the churn-simulation update (CHURN_RATE, decay behavior) — if the
database has zero cancelled subscriptions, this script will stop early
with an error rather than silently produce a meaningless model.

Usage:
    cd backend
    venv\\Scripts\\activate
    python ..\\scripts\\train_churn_model.py

Requires the same DB the backend uses (reads DB_PASS from project-root .env).
Requires: pandas, numpy, sqlalchemy, psycopg2-binary, xgboost, scikit-learn,
python-dotenv, joblib
"""

import os
import sys
from datetime import timedelta

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from xgboost import XGBClassifier
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from sklearn.metrics import (
    accuracy_score, f1_score, fbeta_score, roc_auc_score,
    balanced_accuracy_score, confusion_matrix, classification_report,
)
import joblib

# ── Config ──────────────────────────────────────────────────────
MONTHS = 18  # must match scripts/generate_synthetic_data.py

PLAN_SLOTS = {
    "full": ["breakfast", "lunch", "dinner"],
    "breakfast_only": ["breakfast"],
    "lunch_only": ["lunch"],
    "dinner_only": ["dinner"],
    "breakfast_lunch": ["breakfast", "lunch"],
    "breakfast_dinner": ["breakfast", "dinner"],
    "lunch_dinner": ["lunch", "dinner"],
}

# plan_type as one numeric "how much of the mess does this student rely on"
# signal instead of 7 sparse one-hot columns. The generator's churn logic
# doesn't condition on plan_type at all, so with only ~30-40 real churners,
# 7 extra dummy columns just gives XGBoost room to fit incidental noise
# instead of real signal (this showed up directly in v1's feature importance
# — plan_type dummies ranked above rate_trend).
WEEKLY_MEALS = {
    "full": 21,
    "breakfast_lunch": 14,
    "breakfast_dinner": 14,
    "lunch_dinner": 14,
    "breakfast_only": 7,
    "lunch_only": 7,
    "dinner_only": 7,
}

SNAPSHOT_INTERVAL_DAYS = 7
MIN_HISTORY_DAYS = 30
HORIZON_DAYS = 30

OUTPUT_MODEL_PATH = "churn_model.joblib"
OUTPUT_FEATURES_PATH = "churn_model_features.joblib"
OUTPUT_THRESHOLD_PATH = "churn_model_threshold.joblib"


def build_exam_windows(start, total_days, months):
    """Ported from generate_synthetic_data.py — must stay identical to that source."""
    windows = []
    num_exam_periods = max(2, months // 4)
    spacing = total_days // (num_exam_periods + 1)
    for i in range(1, num_exam_periods + 1):
        w_start = start + timedelta(days=spacing * i)
        w_end = w_start + timedelta(days=10)
        windows.append((w_start, w_end))
    return windows


def in_any_window(d, windows):
    return any(w_start <= d <= w_end for w_start, w_end in windows)


def load_data(engine):
    print("Loading subscriptions, attendance, ratings, complaints from the database...")
    subs = pd.read_sql("""
        SELECT s.user_id, s.plan_type, s.status, s.start_date, s.end_date
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE u.email LIKE 'synth%%'
    """, engine)

    attendance = pd.read_sql("""
        SELECT a.user_id, a.date, a.slot
        FROM attendance a
        WHERE a.qr_token = 'synthetic'
    """, engine)

    ratings = pd.read_sql("""
        SELECT r.user_id, m.date, r.score
        FROM ratings r
        JOIN menus m ON r.menu_id = m.id
        JOIN users u ON r.user_id = u.id
        WHERE u.email LIKE 'synth%%'
    """, engine)

    complaints = pd.read_sql("""
        SELECT c.user_id, c.created_at::date AS date
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        WHERE u.email LIKE 'synth%%'
    """, engine)

    n_churned = (subs['status'] == 'cancelled').sum()
    print(f"  Subscriptions: {subs.shape}  | churned: {n_churned}")
    print(f"  Attendance:    {attendance.shape}")
    print(f"  Ratings:       {ratings.shape}")
    print(f"  Complaints:    {complaints.shape}")

    if n_churned == 0:
        print("ERROR: No cancelled subscriptions found. Re-run "
              "scripts/generate_synthetic_data.py (the version with CHURN_RATE) "
              "before running this script.")
        sys.exit(1)

    return subs, attendance, ratings, complaints


def build_daily_eligibility(subs, attendance):
    print("Building daily eligibility grid + daily attendance rate...")
    rows = []
    for _, sub in subs.iterrows():
        date_range = pd.date_range(sub['start_date'], sub['end_date'], freq='D')
        n_slots = len(PLAN_SLOTS[sub['plan_type']])
        for d in date_range:
            rows.append((sub['user_id'], d, n_slots))

    grid = pd.DataFrame(rows, columns=['user_id', 'date', 'eligible_slots'])
    grid['date'] = pd.to_datetime(grid['date'])

    attendance = attendance.copy()
    attendance['date'] = pd.to_datetime(attendance['date'])
    daily_attended = (
        attendance.groupby(['user_id', 'date'])
                   .size()
                   .reset_index(name='attended_slots')
    )

    daily = grid.merge(daily_attended, on=['user_id', 'date'], how='left')
    daily['attended_slots'] = daily['attended_slots'].fillna(0)
    daily['daily_rate'] = (daily['attended_slots'] / daily['eligible_slots']).clip(0, 1)

    print(f"  Daily eligibility rows: {daily.shape}")
    return daily


def add_rolling(df, col, window, out_col, agg='mean'):
    df[out_col] = (
        df.groupby('user_id')[col]
          .transform(lambda s: s.shift(1).rolling(window, min_periods=3).agg(agg))
    )
    return df


def engineer_daily_features(daily, ratings, complaints):
    print("Engineering causal rolling features (rate_7d/14d/30d, trend, ratings, complaints)...")
    daily = daily.sort_values(['user_id', 'date']).reset_index(drop=True)

    daily = add_rolling(daily, 'daily_rate', 7, 'rate_7d')
    daily = add_rolling(daily, 'daily_rate', 14, 'rate_14d')
    daily = add_rolling(daily, 'daily_rate', 30, 'rate_30d')

    global_mean = daily['daily_rate'].mean()
    for c in ['rate_7d', 'rate_14d', 'rate_30d']:
        daily[c] = daily[c].fillna(global_mean)

    daily['rate_trend'] = daily['rate_7d'] - daily['rate_30d']

    ratings = ratings.copy()
    ratings['date'] = pd.to_datetime(ratings['date'])
    daily_rating = ratings.groupby(['user_id', 'date'])['score'].mean().reset_index(name='daily_score')
    daily = daily.merge(daily_rating, on=['user_id', 'date'], how='left')
    daily['daily_score'] = daily['daily_score'].fillna(0)
    daily = add_rolling(daily, 'daily_score', 30, 'avg_rating_30d')
    global_rating_mean = ratings['score'].mean()
    daily['avg_rating_30d'] = daily['avg_rating_30d'].replace(0, np.nan).fillna(global_rating_mean)

    complaints = complaints.copy()
    complaints['date'] = pd.to_datetime(complaints['date'])
    daily_complaints = complaints.groupby(['user_id', 'date']).size().reset_index(name='complaint_flag')
    daily = daily.merge(daily_complaints, on=['user_id', 'date'], how='left')
    daily['complaint_flag'] = daily['complaint_flag'].fillna(0)
    daily = add_rolling(daily, 'complaint_flag', 30, 'complaint_count_30d', agg='sum')
    daily['complaint_count_30d'] = daily['complaint_count_30d'].fillna(0)

    return daily


def build_snapshots(daily, subs):
    print("Building snapshot dataset (one row per student every "
          f"{SNAPSHOT_INTERVAL_DAYS} days of tenure)...")
    data_start = daily['date'].min()
    data_end = daily['date'].max()
    total_days = (data_end - data_start).days + 1
    exam_windows = build_exam_windows(data_start, total_days, MONTHS)
    print(f"  Exam windows ({len(exam_windows)}):")
    for w_start, w_end in exam_windows:
        print(f"    {w_start.date()} -> {w_end.date()}")

    daily_indexed = daily.set_index(['user_id', 'date'])

    snapshot_rows = []
    for _, sub in subs.iterrows():
        uid = sub['user_id']
        is_churner = sub['status'] == 'cancelled'
        sub_end = pd.Timestamp(sub['end_date'])
        sub_start = pd.Timestamp(sub['start_date'])

        first_snapshot = sub_start + timedelta(days=MIN_HISTORY_DAYS)
        last_snapshot = sub_end - timedelta(days=1)
        if first_snapshot >= last_snapshot:
            continue

        snap_dates = pd.date_range(first_snapshot, last_snapshot, freq=f'{SNAPSHOT_INTERVAL_DAYS}D')

        for s in snap_dates:
            try:
                row = daily_indexed.loc[(uid, s)]
            except KeyError:
                continue

            label = int(is_churner and (sub_end - s).days <= HORIZON_DAYS)

            snapshot_rows.append({
                'user_id': uid,
                'snapshot_date': s,
                'plan_type': sub['plan_type'],
                'tenure_days': (s - sub_start).days,
                'rate_7d': row['rate_7d'],
                'rate_14d': row['rate_14d'],
                'rate_30d': row['rate_30d'],
                'rate_trend': row['rate_trend'],
                'avg_rating_30d': row['avg_rating_30d'],
                'complaint_count_30d': row['complaint_count_30d'],
                'is_weekend': int(s.dayofweek >= 5),
                'is_exam_period': int(in_any_window(s, exam_windows)),
                'will_churn_30d': label,
            })

    snapshots = pd.DataFrame(snapshot_rows)
    snapshots['weekly_meals'] = snapshots['plan_type'].map(WEEKLY_MEALS)
    snapshots = snapshots.drop(columns=['plan_type'])

    print(f"  Snapshot dataset: {snapshots.shape}")
    print(f"  Positive rate (will_churn_30d=1): {snapshots['will_churn_30d'].mean():.4f}")
    print(f"  Unique students represented: {snapshots['user_id'].nunique()}")
    return snapshots


def split_data(snapshots):
    cutoff_date = snapshots['snapshot_date'].quantile(0.8, interpolation='nearest')
    print(f"Train/test cutoff date: {cutoff_date}")

    train = snapshots[snapshots['snapshot_date'] < cutoff_date]
    test = snapshots[snapshots['snapshot_date'] >= cutoff_date]

    feature_cols = [c for c in snapshots.columns if c not in ['user_id', 'snapshot_date', 'will_churn_30d']]

    X_train, y_train = train[feature_cols], train['will_churn_30d']
    X_test, y_test = test[feature_cols], test['will_churn_30d']

    print(f"  Train: {X_train.shape}  Test: {X_test.shape}")
    print(f"  Train churn rate: {y_train.mean():.4f}  Test churn rate: {y_test.mean():.4f}")
    return train, test, X_train, y_train, X_test, y_test, feature_cols


def tune_hyperparameters(X_train, y_train):
    print("Tuning hyperparameters (RandomizedSearchCV + TimeSeriesSplit)...")
    param_dist = {
        'n_estimators': [100, 200, 300, 400],
        'max_depth': [2, 3, 4, 5],
        'learning_rate': [0.01, 0.03, 0.05, 0.1],
        'subsample': [0.6, 0.7, 0.8, 0.9],
        'colsample_bytree': [0.6, 0.7, 0.8, 0.9],
        'min_child_weight': [3, 5, 7, 10, 15],
        'gamma': [0.1, 0.3, 0.5, 0.8, 1.0],
    }
    base_model = XGBClassifier(eval_metric='logloss', random_state=42)
    tscv = TimeSeriesSplit(n_splits=4)

    search = RandomizedSearchCV(
        base_model, param_distributions=param_dist, n_iter=40,
        scoring='f1', cv=tscv, n_jobs=-1, random_state=42, verbose=1,
    )
    search.fit(X_train, y_train)

    print("  Best params:", search.best_params_)
    print("  Best CV F1: ", round(search.best_score_, 4))
    return search.best_params_


def tune_threshold(train, feature_cols, best_params):
    print("Tuning decision threshold on a held-out validation split (recall-weighted, F2)...")
    val_cutoff = train['snapshot_date'].quantile(0.85, interpolation='nearest')
    train_fit = train[train['snapshot_date'] < val_cutoff]
    val = train[train['snapshot_date'] >= val_cutoff]

    X_train_fit, y_train_fit = train_fit[feature_cols], train_fit['will_churn_30d']
    X_val, y_val = val[feature_cols], val['will_churn_30d']

    print(f"  Train-fit: {X_train_fit.shape}  Validation: {X_val.shape}")

    val_model = XGBClassifier(eval_metric='logloss', random_state=42, **best_params)
    val_model.fit(X_train_fit, y_train_fit)
    val_proba = val_model.predict_proba(X_val)[:, 1]

    candidate_thresholds = np.linspace(0.05, 0.95, 181)
    f2_scores = [
        fbeta_score(y_val, (val_proba >= t).astype(int), beta=2, zero_division=0)
        for t in candidate_thresholds
    ]
    best_idx = int(np.argmax(f2_scores))
    best_threshold = candidate_thresholds[best_idx]

    default_pred = (val_proba >= 0.5).astype(int)
    tuned_pred = (val_proba >= best_threshold).astype(int)

    print(f"  Default threshold 0.5   -> F2: {fbeta_score(y_val, default_pred, beta=2, zero_division=0):.4f}"
          f"  | F1: {f1_score(y_val, default_pred, zero_division=0):.4f}"
          f"  | Balanced acc: {balanced_accuracy_score(y_val, default_pred):.4f}")
    print(f"  Best threshold {best_threshold:.3f} -> F2: {f2_scores[best_idx]:.4f}"
          f"  | F1: {f1_score(y_val, tuned_pred, zero_division=0):.4f}"
          f"  | Balanced acc: {balanced_accuracy_score(y_val, tuned_pred):.4f}")
    return best_threshold


def main():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(env_path)
    db_pass = os.getenv("DB_PASS")
    if not db_pass:
        print("ERROR: DB_PASS not found in .env")
        sys.exit(1)

    database_url = f"postgresql://messmate:{db_pass}@localhost:5432/messmate"
    engine = create_engine(database_url)

    subs, attendance, ratings, complaints = load_data(engine)
    daily = build_daily_eligibility(subs, attendance)
    daily = engineer_daily_features(daily, ratings, complaints)
    snapshots = build_snapshots(daily, subs)
    train, test, X_train, y_train, X_test, y_test, feature_cols = split_data(snapshots)

    best_params = tune_hyperparameters(X_train, y_train)
    best_threshold = tune_threshold(train, feature_cols, best_params)

    print("Refitting final model on full training period...")
    model = XGBClassifier(eval_metric='logloss', random_state=42, **best_params)
    model.fit(X_train, y_train)

    y_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= best_threshold).astype(int)

    print(f"\nUsing tuned (F2) threshold: {best_threshold:.3f} (default would be 0.5)")
    print(f"Accuracy:         {accuracy_score(y_test, y_pred):.4f}")
    print(f"F1 score:         {f1_score(y_test, y_pred, zero_division=0):.4f}")
    print(f"F2 score:         {fbeta_score(y_test, y_pred, beta=2, zero_division=0):.4f}")
    print(f"ROC-AUC:          {roc_auc_score(y_test, y_proba):.4f}")
    print(f"Balanced accuracy: {balanced_accuracy_score(y_test, y_pred):.4f}")
    print()
    print(classification_report(y_test, y_pred, target_names=['Stays', 'Churns (30d)']))
    print("Confusion matrix (rows=actual, cols=predicted) [Stays, Churns]:")
    print(confusion_matrix(y_test, y_pred))

    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nTop 15 feature importances:")
    print(importances.head(15))

    joblib.dump(model, OUTPUT_MODEL_PATH)
    joblib.dump(feature_cols, OUTPUT_FEATURES_PATH)
    joblib.dump(best_threshold, OUTPUT_THRESHOLD_PATH)
    print(f"\nSaved: {OUTPUT_MODEL_PATH}")
    print(f"Saved: {OUTPUT_FEATURES_PATH}")
    print(f"Saved: {OUTPUT_THRESHOLD_PATH} ({best_threshold:.3f})")

    print("\nNote: this script does not include the Gemini retention-message drafting "
          "step from the notebook. That stays in notebooks/churn_model.ipynb for now — "
          "it's a demo/reporting feature, not part of the retraining pipeline. It can be "
          "wired into a FastAPI endpoint separately once the churn model itself is live.")


if __name__ == "__main__":
    main()
