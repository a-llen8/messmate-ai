"""
MessMate — Week 6: Attendance Forecasting Model (script version)

Clean, linear script version of notebooks/week6_attendance_model.ipynb, for use in
a retraining pipeline or by a backend service — no cells, no inline plots, just
train -> evaluate -> save.

Predicts: will THIS student attend THIS meal slot on a given date (per-student
binary classification), not a headcount/demand forecast.

Usage:
    cd backend
    venv\\Scripts\\activate
    python ..\\scripts\\train_attendance_model.py

Requires the same DB the backend uses (reads DB_PASS from backend/.env).
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
    accuracy_score, f1_score, roc_auc_score,
    balanced_accuracy_score, classification_report,
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

BUFFER_DAYS = 7

OUTPUT_MODEL_PATH = "attendance_model.joblib"
OUTPUT_FEATURES_PATH = "attendance_model_features.joblib"
OUTPUT_THRESHOLD_PATH = "attendance_model_threshold.joblib"


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


def build_eligibility_grid(subs, attendance):
    print("Building eligibility grid...")
    rows = []
    for _, sub in subs.iterrows():
        date_range = pd.date_range(sub['start_date'], sub['end_date'], freq='D')
        slots = PLAN_SLOTS[sub['plan_type']]
        for d in date_range:
            for slot in slots:
                rows.append((sub['user_id'], d, slot, sub['plan_type']))

    grid = pd.DataFrame(rows, columns=['user_id', 'date', 'slot', 'plan_type'])
    grid['date'] = pd.to_datetime(grid['date']).dt.date

    attendance = attendance.copy()
    attendance['date'] = pd.to_datetime(attendance['date']).dt.date
    attendance['attended'] = 1

    data = grid.merge(
        attendance[['user_id', 'date', 'slot', 'attended']],
        on=['user_id', 'date', 'slot'], how='left'
    )
    data['attended'] = data['attended'].fillna(0).astype(int)

    print(f"  Final labeled dataset: {data.shape}")
    print(f"  Attendance rate: {data['attended'].mean():.3f}")
    return data


def engineer_features(data):
    print("Engineering features...")
    data['date'] = pd.to_datetime(data['date'])
    data = data.sort_values(['user_id', 'date']).reset_index(drop=True)

    data['day_of_week'] = data['date'].dt.dayofweek
    data['is_weekend'] = (data['day_of_week'] >= 5).astype(int)
    data['month'] = data['date'].dt.month

    def add_rolling_rate(df, window, colname):
        df[colname] = (
            df.groupby('user_id')['attended']
              .transform(lambda s: s.shift(1).rolling(window, min_periods=3).mean())
        )
        return df

    data = add_rolling_rate(data, 7, 'rate_7d')
    data = add_rolling_rate(data, 14, 'rate_14d')
    data = add_rolling_rate(data, 30, 'rate_30d')

    data['rate_overall'] = (
        data.groupby('user_id')['attended']
            .transform(lambda s: s.shift(1).expanding(min_periods=3).mean())
    )

    # global_mean computed from TRAIN rows only (pre-cutoff) — no test-set leakage
    train_cutoff_for_mean = data['date'].quantile(0.8, interpolation='nearest')
    global_mean = data.loc[data['date'] < train_cutoff_for_mean, 'attended'].mean()

    for col in ['rate_7d', 'rate_14d', 'rate_30d', 'rate_overall']:
        data[col] = data[col].fillna(global_mean)

    data = pd.get_dummies(data, columns=['slot', 'plan_type'], drop_first=False)

    # exam calendar features (pure date lookups — no leakage)
    start_date = data['date'].min()
    end_date = data['date'].max()
    total_days = (end_date - start_date).days + 1
    exam_windows = build_exam_windows(start_date, total_days, MONTHS)
    print(f"  Exam windows ({len(exam_windows)}):")
    for w_start, w_end in exam_windows:
        print(f"    {w_start.date()} -> {w_end.date()}")

    data['is_exam_period'] = data['date'].apply(lambda d: int(in_any_window(d, exam_windows)))
    data['exam_proximity'] = data['date'].apply(lambda d: exam_proximity_score(d, exam_windows))

    # causal last-time-this-slot feature
    slot_dummy_cols = [c for c in data.columns if c.startswith('slot_')]
    data['_slot_tmp'] = data[slot_dummy_cols].idxmax(axis=1).str.replace('slot_', '', regex=False)
    data = data.sort_values(['user_id', '_slot_tmp', 'date']).reset_index(drop=True)
    data['attended_last_same_slot'] = (
        data.groupby(['user_id', '_slot_tmp'])['attended']
            .transform(lambda s: s.shift(1))
    )
    data['attended_last_same_slot'] = data['attended_last_same_slot'].fillna(global_mean)
    data = data.drop(columns=['_slot_tmp'])
    data = data.sort_values(['user_id', 'date']).reset_index(drop=True)

    return data


def split_data(data):
    cutoff_date = data['date'].quantile(0.8, interpolation='nearest')
    print(f"Train/test cutoff date: {cutoff_date}")

    train = data[data['date'] < cutoff_date]
    test = data[data['date'] >= cutoff_date]

    feature_cols = [c for c in data.columns if c not in ['user_id', 'date', 'attended']]

    X_train, y_train = train[feature_cols], train['attended']
    X_test, y_test = test[feature_cols], test['attended']

    print(f"  Train: {X_train.shape}  Test: {X_test.shape}")
    print(f"  Train attendance rate: {y_train.mean():.3f}  Test attendance rate: {y_test.mean():.3f}")
    return train, test, X_train, y_train, X_test, y_test, feature_cols


def tune_hyperparameters(X_train, y_train):
    print("Tuning hyperparameters (RandomizedSearchCV + TimeSeriesSplit)...")
    param_dist = {
        'n_estimators': [200, 300, 400, 600],
        'max_depth': [3, 4, 5, 6, 8],
        'learning_rate': [0.01, 0.03, 0.05, 0.1],
        'subsample': [0.6, 0.7, 0.8, 0.9, 1.0],
        'colsample_bytree': [0.6, 0.7, 0.8, 0.9, 1.0],
        'min_child_weight': [1, 3, 5, 7],
        'gamma': [0, 0.1, 0.3, 0.5],
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
    print("Tuning decision threshold on a held-out validation split...")
    val_cutoff = train['date'].quantile(0.85, interpolation='nearest')
    train_fit = train[train['date'] < val_cutoff]
    val = train[train['date'] >= val_cutoff]

    X_train_fit, y_train_fit = train_fit[feature_cols], train_fit['attended']
    X_val, y_val = val[feature_cols], val['attended']

    val_model = XGBClassifier(eval_metric='logloss', random_state=42, **best_params)
    val_model.fit(X_train_fit, y_train_fit)
    val_proba = val_model.predict_proba(X_val)[:, 1]

    candidate_thresholds = np.linspace(0.05, 0.95, 181)
    balanced_scores = [
        balanced_accuracy_score(y_val, (val_proba >= t).astype(int))
        for t in candidate_thresholds
    ]
    best_idx = int(np.argmax(balanced_scores))
    best_threshold = candidate_thresholds[best_idx]

    default_pred = (val_proba >= 0.5).astype(int)
    print(f"  Default threshold 0.5   -> validation balanced accuracy: {balanced_accuracy_score(y_val, default_pred):.4f}")
    print(f"  Best threshold {best_threshold:.3f} -> validation balanced accuracy: {balanced_scores[best_idx]:.4f}")
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

    subs, attendance = load_data(engine)
    data = build_eligibility_grid(subs, attendance)
    data = engineer_features(data)
    train, test, X_train, y_train, X_test, y_test, feature_cols = split_data(data)

    best_params = tune_hyperparameters(X_train, y_train)
    best_threshold = tune_threshold(train, feature_cols, best_params)

    print("Refitting final model on full training period...")
    model = XGBClassifier(eval_metric='logloss', random_state=42, **best_params)
    model.fit(X_train, y_train)

    y_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= best_threshold).astype(int)

    print(f"\nUsing tuned threshold: {best_threshold:.3f} (default would be 0.5)")
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(f"F1 score: {f1_score(y_test, y_pred):.4f}")
    print(f"ROC-AUC:  {roc_auc_score(y_test, y_proba):.4f}")
    print()
    print(classification_report(y_test, y_pred))

    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("Top 10 feature importances:")
    print(importances.head(10))

    joblib.dump(model, OUTPUT_MODEL_PATH)
    joblib.dump(feature_cols, OUTPUT_FEATURES_PATH)
    joblib.dump(best_threshold, OUTPUT_THRESHOLD_PATH)
    print(f"\nSaved: {OUTPUT_MODEL_PATH}")
    print(f"Saved: {OUTPUT_FEATURES_PATH}")
    print(f"Saved: {OUTPUT_THRESHOLD_PATH} ({best_threshold:.3f})")


if __name__ == "__main__":
    main()
