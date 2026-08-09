"""
MessMate — Caterer Ops Agent tools.

Each tool is a plain Python function wrapping an existing model artifact
or SQL query, plus a matching google-genai FunctionDeclaration the model
chooses to call (or not) each round — the loop in ops_agent.py does not
hardcode which tools get called or in what order.

get_churn_risk and get_headcount_forecast wrap backend/app/ml/inference.py.
get_complaint_cluster_trend wraps the HDBSCAN clusterer trained by
scripts/train_complaint_clusters.py (fixed — see that script's docstring
for the UMAP dimensionality-reduction fix that made real clusters possible;
was previously stubbed/parked because it found 0 clusters).
"""

import os
from pathlib import Path
from datetime import date as _date, timedelta

import joblib
import pandas as pd
from google.genai import types

from app.ml import inference
from app.core.database import engine  # reuse the app's real DB connection —
# NOT a hardcoded localhost URL like the offline training scripts use, since
# this runs against whatever DB the deployed app is pointed at (Supabase in
# production via the GitHub Actions cron, local Docker in dev)


# ── get_churn_risk ────────────────────────────────────────────────────
TOOL_CHURN_RISK = types.FunctionDeclaration(
    name="get_churn_risk",
    description=(
        "Look up currently-active students at or above the tuned churn-risk "
        "threshold, scored as of today. Returns each student's churn "
        "probability, attendance trend, recent complaints, and rating history. "
        "Call this to check whether any students need a retention check-in."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "description": "Max students to return, highest risk first. Default 15.",
            }
        },
    },
)


def call_get_churn_risk(top_n: int = 15) -> dict:
    students = inference.get_at_risk_students(top_n=top_n)
    return {
        "at_risk_count": len(students),
        "students": students,
    }


# ── get_headcount_forecast ───────────────────────────────────────────────
TOOL_HEADCOUNT = types.FunctionDeclaration(
    name="get_headcount_forecast",
    description=(
        "Predict tomorrow's headcount for each meal slot (breakfast, lunch, "
        "dinner), so the caterer can plan prep quantities. Returns predicted "
        "headcount, eligible student count, and recent 7-day average per slot. "
        "Call this to check whether any slot needs a prep-quantity heads-up."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "target_date": {
                "type": "string",
                "format": "date",
                "description": "Date to forecast, YYYY-MM-DD. Defaults to tomorrow if omitted.",
            }
        },
    },
)


def call_get_headcount_forecast(target_date: str | None = None) -> dict:
    from datetime import date as _date2

    parsed = _date2.fromisoformat(target_date) if target_date else None
    forecast = inference.get_headcount_forecast(target_date=parsed)
    return {"forecast": forecast}


# ── get_complaint_cluster_trend ───────────────────────────────────────────
TOOL_COMPLAINT_TREND = types.FunctionDeclaration(
    name="get_complaint_cluster_trend",
    description=(
        "Look up trending complaint clusters over the last N days, with "
        "cluster labels and counts (e.g. 'Excessive wait times', 'Poor "
        "sanitation and unclean counters'). Call this to check whether a "
        "specific recurring issue — not just an isolated complaint — needs "
        "addressing."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Lookback window in days. Default 14.",
            }
        },
    },
)

# Artifacts produced by scripts/train_complaint_clusters.py, saved to the
# same directory as the other production models (churn_model.joblib,
# headcount_model.joblib, attendance_model.joblib) — this exact path has
# explicit .gitignore exceptions carved out of the blanket *.joblib rule,
# so these are the files that actually get committed and are present when
# GitHub Actions checks out the repo fresh for the daily cron run.
_ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "ml" / "models"  # app/agents/ -> app/ml/models/
_CLUSTERER_PATH = _ARTIFACT_DIR / "complaint_clusterer.joblib"
_REDUCER_PATH = _ARTIFACT_DIR / "complaint_umap_reducer.joblib"
_LABELS_PATH = _ARTIFACT_DIR / "complaint_cluster_labels.joblib"

# Lazy-loaded module-level cache — loaded once per process (per Ops Agent
# run), not once per tool call, since embedding-model + artifact loading
# is the slow part.
_complaint_artifacts = {}


def _load_complaint_cluster_artifacts():
    if not _complaint_artifacts:
        for path in (_CLUSTERER_PATH, _REDUCER_PATH, _LABELS_PATH):
            if not path.exists():
                raise FileNotFoundError(
                    f"Complaint cluster artifact missing: {path}. "
                    "Run scripts/train_complaint_clusters.py first, and make "
                    "sure the .joblib outputs are committed to git (check "
                    ".gitignore exceptions for backend/app/ml/models/)."
                )
        _complaint_artifacts["clusterer"] = joblib.load(_CLUSTERER_PATH)
        _complaint_artifacts["reducer"] = joblib.load(_REDUCER_PATH)
        _complaint_artifacts["labels"] = joblib.load(_LABELS_PATH)

        from sentence_transformers import SentenceTransformer
        _complaint_artifacts["embedding_model"] = SentenceTransformer("all-MiniLM-L6-v2")

    return (
        _complaint_artifacts["clusterer"],
        _complaint_artifacts["reducer"],
        _complaint_artifacts["labels"],
        _complaint_artifacts["embedding_model"],
    )


def call_get_complaint_cluster_trend(days: int = 14) -> dict:
    import hdbscan  # only needed for approximate_predict; imported lazily like
                     # the embedding model, so the rest of the module doesn't
                     # require ML deps to be installed if this tool is never called

    clusterer, reducer, labels, embedding_model = _load_complaint_cluster_artifacts()

    cutoff = _date.today() - timedelta(days=days)
    complaints = pd.read_sql(
        """
        SELECT id, text, category, created_at
        FROM complaints
        WHERE created_at >= %(cutoff)s
        ORDER BY created_at
        """,
        engine,
        params={"cutoff": cutoff},
    )

    if len(complaints) == 0:
        return {"window_days": days, "total_complaints": 0, "clusters": []}

    embeddings = embedding_model.encode(
        complaints["text"].tolist(), convert_to_numpy=True
    )
    # IMPORTANT: transform, never fit_transform — the reducer was already
    # fit during training; refitting here would silently produce wrong
    # cluster assignments against the trained clusterer's coordinate space.
    reduced = reducer.transform(embeddings)
    cluster_ids, _strengths = hdbscan.approximate_predict(clusterer, reduced)

    complaints = complaints.copy()
    complaints["cluster_id"] = cluster_ids

    summary = (
        complaints.groupby("cluster_id")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    clusters = []
    for _, row in summary.iterrows():
        cid = int(row["cluster_id"])
        label_info = labels.get(cid, {"label": "Uncategorized / one-off"})
        clusters.append({
            "cluster_id": cid,
            "label": label_info["label"],
            "count": int(row["count"]),
        })

    return {
        "window_days": days,
        "total_complaints": len(complaints),
        "clusters": clusters,
    }


# ── Registry ─────────────────────────────────────────────────────────────
# ALL_TOOLS holds every tool's FunctionDeclaration, regardless of cadence.
# Which ones are actually offered to the model on a given run is decided by
# get_active_tools(run_mode) below — NOT by editing this list directly.
ALL_TOOLS: list[types.FunctionDeclaration] = [
    TOOL_CHURN_RISK, TOOL_HEADCOUNT, TOOL_COMPLAINT_TREND,
]

TOOL_REGISTRY = {
    "get_churn_risk": call_get_churn_risk,
    "get_headcount_forecast": call_get_headcount_forecast,
    "get_complaint_cluster_trend": call_get_complaint_cluster_trend,
}

# One mode per tool. This is the single source of truth for which GitHub
# Actions schedule a given tool belongs to — the daily/weekly/monthly
# workflow YAMLs don't decide this, they just set RUN_MODE and this map
# does the routing. Update THIS if a tool's cadence ever changes, not the
# workflow files.
TOOL_CADENCE: dict[str, str] = {
    "get_headcount_forecast": "daily",
    "get_churn_risk": "weekly",
    "get_complaint_cluster_trend": "monthly",
}

VALID_RUN_MODES = frozenset(TOOL_CADENCE.values())  # {"daily", "weekly", "monthly"}

def get_active_tools(run_mode: str) -> list[types.FunctionDeclaration]:
    """Returns the FunctionDeclaration(s) whose cadence matches run_mode.
    Each run_mode currently maps to exactly one tool (daily->headcount,
    weekly->churn, monthly->complaint) — if that ever changes to multiple
    tools per mode, this function's behavior (filter, not fixed-index)
    still holds without changes here.
    """
    if run_mode not in VALID_RUN_MODES:
        raise ValueError(
            f"Unknown RUN_MODE '{run_mode}'. Must be one of {sorted(VALID_RUN_MODES)}."
        )
    return [tool for tool in ALL_TOOLS if TOOL_CADENCE[tool.name] == run_mode]