"""
MessMate — Caterer Ops Agent structured output schema.

This is what the agent loop validates the model's final `submit_decision`
tool call against (see ops_agent.py). Nothing in here executes anything —
every action is caterer-facing text the dashboard shows for approve/edit/
reject, per the human-in-the-loop design decision.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ActionPriority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ActionCategory(str, Enum):
    churn_retention = "churn_retention"
    headcount_prep = "headcount_prep"
    complaint_followup = "complaint_followup"  # unused until the complaints tool is wired in
    general = "general"


class AgentAction(BaseModel):
    category: ActionCategory
    priority: ActionPriority
    summary: str = Field(..., description="One-line description of the finding, for the dashboard list view")
    reasoning: str = Field(..., description="Why this was flagged — should reference specific tool output, not just assert a conclusion")
    drafted_message: Optional[str] = Field(
        None, description="Caterer-facing message ready to send/edit, e.g. a student check-in. Omit for actions with no message to send."
    )
    related_user_id: Optional[int] = Field(None, description="Set for per-student actions (e.g. churn_retention)")
    related_date: Optional[date] = Field(None, description="Set for date-specific actions (e.g. headcount_prep)")

    @field_validator("summary", "reasoning")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v


class OpsAgentDecision(BaseModel):
    run_date: date
    summary: str = Field(..., description="2-3 sentence overview for the caterer dashboard header")
    actions: list[AgentAction] = Field(default_factory=list)
    tools_consulted: list[str] = Field(
        default_factory=list, description="Names of tools actually called this run — filled in by the loop controller, not the model"
    )

    @field_validator("actions")
    @classmethod
    def _cap_actions(cls, v: list[AgentAction]) -> list[AgentAction]:
        if len(v) > 25:
            raise ValueError("too many actions in one run (>25) — likely a prompt/loop issue, not real signal")
        return v


# Hand-written JSON schema for the `submit_decision` function declaration.
# NOT derived from OpsAgentDecision.model_json_schema() — pydantic v2 emits
# $defs/$ref for nested models, which is inconsistent across function-calling
# schema parsers. This is kept flat and manually mirrored to the model above;
# if you add/change a field on AgentAction or OpsAgentDecision, update this too.
SUBMIT_DECISION_PARAMETERS_SCHEMA = {
    "type": "object",
    "properties": {
        "run_date": {"type": "string", "format": "date", "description": "Today's date, YYYY-MM-DD"},
        "summary": {"type": "string", "description": "2-3 sentence overview for the caterer dashboard header"},
        "actions": {
            "type": "array",
            "maxItems": 25,
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["churn_retention", "headcount_prep", "complaint_followup", "general"],
                    },
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "summary": {"type": "string", "description": "One-line description for the dashboard list view"},
                    "reasoning": {
                        "type": "string",
                        "description": "Why this was flagged — reference specific tool output (numbers, names), not a vague assertion",
                    },
                    "drafted_message": {
                        "type": "string",
                        "description": "Caterer-facing message ready to send/edit. Omit if this action has nothing to send.",
                    },
                    "related_user_id": {"type": "integer", "description": "Set for per-student actions"},
                    "related_date": {"type": "string", "format": "date", "description": "Set for date-specific actions"},
                },
                "required": ["category", "priority", "summary", "reasoning"],
            },
        },
    },
    "required": ["run_date", "summary", "actions"],
}