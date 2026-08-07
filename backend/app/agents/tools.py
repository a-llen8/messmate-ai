"""
MessMate — Caterer Ops Agent tools.

Each tool is a plain Python function wrapping an existing model artifact
or SQL query, plus a matching google-genai FunctionDeclaration the model
chooses to call (or not) each round — the loop in ops_agent.py does not
hardcode which tools get called or in what order.

Only churn + headcount are wired in below. Complaint cluster trend is
PARKED until the Week 5 synthetic-data paraphrasing fix lands (see
scripts/generate_synthetic_data.py note) — HDBSCAN currently finds 0 real
clusters because there are only 15 unique complaint strings. A stub is
included at the bottom, commented out, so wiring it in later is a matter
of uncommenting + adding it to ACTIVE_TOOLS, not restructuring anything.
"""

from google.genai import types

from app.ml import inference

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
    from datetime import date as _date

    parsed = _date.fromisoformat(target_date) if target_date else None
    forecast = inference.get_headcount_forecast(target_date=parsed)
    return {"forecast": forecast}


# ── Registry ─────────────────────────────────────────────────────────────
# Add TOOL_COMPLAINT_TREND / call_get_complaint_cluster_trend to both of
# these once the Week 5 paraphrasing fix lands and
# scripts/train_complaint_clusters.py produces real clusters.
ACTIVE_TOOLS: list[types.FunctionDeclaration] = [TOOL_CHURN_RISK, TOOL_HEADCOUNT]

TOOL_REGISTRY = {
    "get_churn_risk": call_get_churn_risk,
    "get_headcount_forecast": call_get_headcount_forecast,
}


# ── PARKED: complaint cluster trend ──────────────────────────────────────
# TOOL_COMPLAINT_TREND = types.FunctionDeclaration(
#     name="get_complaint_cluster_trend",
#     description=(
#         "Look up trending complaint clusters over the last N days, with "
#         "cluster labels and counts. Call this to check whether a specific "
#         "recurring issue (not just isolated complaints) needs addressing."
#     ),
#     parameters_json_schema={
#         "type": "object",
#         "properties": {
#             "days": {"type": "integer", "description": "Lookback window in days. Default 14."}
#         },
#     },
# )
#
# def call_get_complaint_cluster_trend(days: int = 14) -> dict:
#     # wraps scripts/train_complaint_clusters.py output once it produces
#     # real clusters instead of 0
#     raise NotImplementedError("blocked on Week 5 synthetic-data paraphrasing fix")