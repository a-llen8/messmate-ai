"""
MessMate — Week 7: Headcount Forecasting Model (waste-reduction agent)

Predicts: how many students will actually attend a given meal slot on a
given date (an aggregate demand number), NOT a per-student prediction.
This is what a caterer can use to decide how much food to prepare —
the model behind the "waste-reduction agent."

Different in kind from Week 6 (attendance) and Week 7 (churn):
those are classification models (yes/no, with a tuned decision threshold).
This is a REGRESSION model (predicts a count), evaluated with MAE/RMSE,
not accuracy/F1/threshold.

Usage:
    cd backend
    venv\\Scripts\\activate
    python ..\\scripts\\train_headcount_model.py

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
from xgboost import XGBRegressor
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error
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

BUFFER_DAYS = 7

OUTPUT_MODEL_PATH = "headcount_model.joblib"
OUTPUT_FEATURES_PATH = "headcount_model_features.joblib"


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


def exam_proximity_score(d, windows, buffer_days=BUFFER_DAYS):
    best = 0.0
    for w_start, w_end in windows:
        if w_start <= d <= w_end:
            return 1.0
        dist = (w_start - d).days if d < w_start else (d - w_end).days
        best = max(best, max(0.0, 1 - dist / buffer_days))
    return best


def load_data(engine):
    print("Loading subscriptions and attendance from the database...")
    subs = pd.read_sql("""
        SELECT s.user_id, s.plan_type, s.start_date, s.end_date
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE u.email LIKE 'synth%%'
    """, engine)

    attendance = pd.read_sql("""
        SELECT a.user_id, a.date, a.slot
        FROM attendance a
        WHERE a.qr_token = 'synthetic'
    """, engine)

    print(f"  Subscriptions: {subs.shape}")
    print(f"  Attendance:    {attendance.shape}")
    return subs, attendance


def _safe_bound(value, fallback: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return fallback if pd.isna(ts) else ts


def build_daily_headcount(subs, attendance):
    """
    Aggregate up to one row per (date, slot): how many students were
    ELIGIBLE for that slot that day, and how many actually ATTENDED.
    This is the same eligibility-grid idea as Week 6, just summed instead
    of kept per-student.
    """
    print("Building daily eligible-count grid...")
    elig_rows = []
    for _, sub in subs.iterrows():
        end = _safe_bound(sub['end_date'], attendance['date'].max())
        date_range = pd.date_range(sub['start_date'], end, freq='D')
        slots = PLAN_SLOTS[sub['plan_type']]
        for d in date_range:
            for slot in slots:
                elig_rows.append((d, slot))

    elig = pd.DataFrame(elig_rows, columns=['date', 'slot'])
    elig['date'] = pd.to_datetime(elig['date'])
    eligible_counts = (
        elig.groupby(['date', 'slot']).size().reset_index(name='eligible_students')
    )

    print("Aggregating actual headcount from attendance...")
    attendance = attendance.copy()
    attendance['date'] = pd.to_datetime(attendance['date'])
    headcount = (
        attendance.groupby(['date', 'slot']).size().reset_index(name='headcount')
    )

    data = eligible_counts.merge(headcount, on=['date', 'slot'], how='left')
    data['headcount'] = data['headcount'].fillna(0).astype(int)

    data = data[data['eligible_students'] > 0].reset_index(drop=True)

    print(f"  Daily (date, slot) rows: {data.shape}")
    print(f"  Avg headcount: {data['headcount'].mean():.1f}  "
          f"Avg eligible: {data['eligible_students'].mean():.1f}")
    return data


def engineer_features(data):
    print("Engineering features...")
    data = data.sort_values(['slot', 'date']).reset_index(drop=True)

    data['day_of_week'] = data['date'].dt.dayofweek
    data['is_weekend'] = (data['day_of_week'] >= 5).astype(int)
    data['month'] = data['date'].dt.month

    def add_rolling(df, col, window, out_col):
        df[out_col] = (
            df.groupby('slot')[col]
              .transform(lambda s: s.shift(1).rolling(window, min_periods=3).mean())
        )
        return df

    data = add_rolling(data, 'headcount', 7, 'avg_headcount_7d')
    data = add_rolling(data, 'headcount', 14, 'avg_headcount_14d')
    data = add_rolling(data, 'headcount', 28, 'avg_headcount_28d')

    data['daily_rate'] = data['headcount'] / data['eligible_students']
    data = add_rolling(data, 'daily_rate', 14, 'avg_rate_14d')

    global_rate_mean = data['daily_rate'].mean()
    for c in ['avg_headcount_7d', 'avg_headcount_14d', 'avg_headcount_28d']:
        data[c] = data[c].fillna(data['headcount'].mean())
    data['avg_rate_14d'] = data['avg_rate_14d'].fillna(global_rate_mean)

    data = pd.get_dummies(data, columns=['slot'], drop_first=False)

    start_date = data['date'].min()
    end_date = data['date'].max()
    total_days = (end_date - start_date).days + 1
    exam_windows = build_exam_windows(start_date, total_days, MONTHS)
    print(f"  Exam windows ({len(exam_windows)}):")
    for w_start, w_end in exam_windows:
        print(f"    {w_start.date()} -> {w_end.date()}")

    data['is_exam_period'] = data['date'].apply(lambda d: int(in_any_window(d, exam_windows)))
    data['exam_proximity'] = data['date'].apply(lambda d: exam_proximity_score(d, exam_windows))

    return data


def split_data(data):
    cutoff_date = data['date'].quantile(0.8, interpolation='nearest')
    print(f"Train/test cutoff date: {cutoff_date}")

    train = data[data['date'] < cutoff_date]
    test = data[data['date'] >= cutoff_date]

    feature_cols = [c for c in data.columns if c not in ['date', 'headcount', 'daily_rate']]

    X_train, y_train = train[feature_cols], train['headcount']
    X_test, y_test = test[feature_cols], test['headcount']

    print(f"  Train: {X_train.shape}  Test: {X_test.shape}")
    print(f"  Train avg headcount: {y_train.mean():.1f}  Test avg headcount: {y_test.mean():.1f}")
    return train, test, X_train, y_train, X_test, y_test, feature_cols


def tune_hyperparameters(X_train, y_train):
    print("Tuning hyperparameters (RandomizedSearchCV + TimeSeriesSplit, scored on MAE)...")
    param_dist = {
        'n_estimators': [200, 300, 400, 600],
        'max_depth': [3, 4, 5, 6, 8],
        'learning_rate': [0.01, 0.03, 0.05, 0.1],
        'subsample': [0.6, 0.7, 0.8, 0.9, 1.0],
        'colsample_bytree': [0.6, 0.7, 0.8, 0.9, 1.0],
        'min_child_weight': [1, 3, 5, 7],
        'gamma': [0, 0.1, 0.3, 0.5],
    }
    base_model = XGBRegressor(random_state=42)
    tscv = TimeSeriesSplit(n_splits=4)

    search = RandomizedSearchCV(
        base_model, param_distributions=param_dist, n_iter=40,
        scoring='neg_mean_absolute_error', cv=tscv, n_jobs=-1, random_state=42, verbose=1,
    )
    search.fit(X_train, y_train)

    print("  Best params:", search.best_params_)
    print("  Best CV MAE:", round(-search.best_score_, 2))
    return search.best_params_


def naive_baseline_mae(train, test):
    """
    Simple sanity-check baseline: predict each slot's headcount as its own
    trailing 7-day rolling average (already computed as avg_headcount_7d).
    If the trained model can't beat this, the extra complexity isn't earning
    its keep — worth knowing either way.
    """
    baseline_pred = test['avg_headcount_7d']
    return mean_absolute_error(test['headcount'], baseline_pred)


def main():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(env_path)
    db_pass = os.getenv("DB_PASS")
    if not db_pass:
        print("ERROR: DB_PASS not found in .env")
        sys.exit(1)

    database_url = f"postgresql://messmate:{db_pass}@localhost:5432/messmate"
    engine = create_engine(database_url)

    subs, attendance = load_data(engine)
    data = build_daily_headcount(subs, attendance)
    data = engineer_features(data)
    train, test, X_train, y_train, X_test, y_test, feature_cols = split_data(data)

    best_params = tune_hyperparameters(X_train, y_train)

    print("Refitting final model on full training period...")
    model = XGBRegressor(random_state=42, **best_params)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_pred = np.clip(y_pred, 0, None)

    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mape = (np.abs(y_test - y_pred) / y_test.replace(0, np.nan)).mean() * 100
    baseline_mae = naive_baseline_mae(train, test)

    print(f"\nMAE:  {mae:.2f} students  (avg test headcount: {y_test.mean():.1f})")
    print(f"RMSE: {rmse:.2f} students")
    print(f"MAPE: {mape:.1f}%")
    print(f"Naive baseline (trailing 7d avg) MAE: {baseline_mae:.2f} students")
    if mae < baseline_mae:
        print(f"  -> Model beats the naive baseline by {baseline_mae - mae:.2f} students MAE.")
    else:
        print("  -> Model does NOT beat the naive baseline — worth investigating before relying on it.")

    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nTop 10 feature importances:")
    print(importances.head(10))

    joblib.dump(model, OUTPUT_MODEL_PATH)
    joblib.dump(feature_cols, OUTPUT_FEATURES_PATH)
    print(f"\nSaved: {OUTPUT_MODEL_PATH}")
    print(f"Saved: {OUTPUT_FEATURES_PATH}")


if __name__ == "__main__":
    main()
