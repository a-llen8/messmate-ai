"""
MessMate — Caterer Ops Agent loop controller.

This is a real agent loop, not a fixed pipeline: each round, Gemini sees
the conversation so far (including every prior tool result) and decides
for itself whether to call another tool or finalize, via a `submit_decision`
function call that IS the finalize action rather than a separate code path
— it goes through the same validate/retry machinery as any other tool call.

All 3 tools (get_headcount_forecast, get_churn_risk, get_complaint_cluster_trend)
are registered in tools.py, but only ONE is active on any given run — which
one is decided by RUN_MODE (daily/weekly/monthly), via
tools.get_active_tools(run_mode). See tools.py's TOOL_CADENCE for the
mode->tool mapping. SYSTEM_PROMPT and the no-function-call nudge below are
both built dynamically per run_mode so the model is never told about a
tool it wasn't given this run.

Run this directly for a manual test (defaults to RUN_MODE=daily if unset):
    cd backend
    venv\\Scripts\\activate
    set RUN_MODE=weekly
    python -m app.agents.ops_agent

Wired to 3 separate GitHub Actions workflows (ops-agent-daily.yml,
ops-agent-weekly.yml, ops-agent-monthly.yml), each setting RUN_MODE and
calling execute_and_save(). There's no celery app instance configured yet
(app/celery/__init__.py is empty), so GitHub Actions cron is the live
scheduler, not Celery beat.
"""

import json
import os
from datetime import date, datetime, timezone

from google import genai
from google.genai import types
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.agents.tools import get_active_tools, TOOL_REGISTRY, VALID_RUN_MODES
from app.agents.schemas import OpsAgentDecision, SUBMIT_DECISION_PARAMETERS_SCHEMA

MODEL_NAME = "gemini-3.1-flash-lite"  # matches notebooks/churn_model.ipynb's retention-message SDK choice
MAX_ROUNDS = 6

SUBMIT_DECISION_TOOL = types.FunctionDeclaration(
    name="submit_decision",
    description=(
        "Finalize this run with your structured decision: a short summary "
        "plus a prioritized list of caterer-facing actions. Call this once "
        "you've consulted the tools you need — do not call it as your first "
        "move without checking at least the tools relevant to today's data."
    ),
    parameters_json_schema=SUBMIT_DECISION_PARAMETERS_SCHEMA,
)

_TOOL_PROMPT_LINES = {
    "get_headcount_forecast": "- get_headcount_forecast: predicted headcount per meal slot for tomorrow",
    "get_churn_risk": "- get_churn_risk: at-risk students, scored today",
    "get_complaint_cluster_trend": "- get_complaint_cluster_trend: trending complaint clusters over the last N days",
}

_RUN_MODE_BLURB = {
    "daily": "review tomorrow's headcount forecast",
    "weekly": "review student churn risk",
    "monthly": "review trending complaint clusters",
}


def _build_system_prompt(run_mode: str, tool_names: list[str]) -> str:
    tool_lines = "\n".join(_TOOL_PROMPT_LINES[name] for name in tool_names)
    plural = "tool" if len(tool_names) == 1 else "tools"
    return f"""You are the MessMate Caterer Ops Agent, running in {run_mode} mode today.

Your job: {_RUN_MODE_BLURB.get(run_mode, "review today's data")}, and decide
what (if anything) the caterer should act on. You have {len(tool_names)} lookup
{plural} and one finalize tool:

{tool_lines}
- submit_decision: finalize your run with a structured decision (call this
  last, after you've checked the data — not as your first move)

Guidelines:
- Only flag genuinely actionable findings. An empty or short actions list
  on a quiet day is correct, not a failure — do not invent action items to
  fill space.
- Every action's `reasoning` must cite specific numbers from a tool result
  (a churn probability, a predicted headcount, a rating), not a vague claim.
- Drafted messages must be short, warm, and non-alarming — never mention
  "churn", "risk", "model", or internal feature names to the recipient.
- Nothing you decide gets sent or executed automatically — the caterer
  approves, edits, or rejects each action in the dashboard. Draft
  accordingly: assume a human reads and can adjust before anything goes out.
- You get up to a few rounds. Check the tool(s) relevant to today, then
  call submit_decision. Don't call the same tool twice unless you have a
  real reason to (e.g. re-checking with a different date).
"""


class TraceEvent:
    """One row's worth of data for agent_traces — a single round's model
    output and/or tool call, kept separate from persistence so the loop
    itself doesn't need a live DB session to run (e.g. for local testing)."""

    def __init__(self, round_num: int, event_type: str, detail: dict):
        self.round_num = round_num
        self.event_type = event_type  # "model_response" | "tool_call" | "tool_result" | "error"
        self.detail = detail
        self.timestamp = datetime.now(timezone.utc)


class OpsAgentRunResult:
    def __init__(self):
        self.decision: OpsAgentDecision | None = None
        self.traces: list[TraceEvent] = []
        self.tools_consulted: list[str] = []
        self.status = "incomplete"  # "completed" | "incomplete" | "error"
        self.error: str | None = None


def _run_tool_call(name: str, args: dict, result: OpsAgentRunResult, round_num: int) -> dict:
    """Executes a tool call, returns the dict to send back as the function
    response's `response` payload. Never raises — malformed/failed calls
    become an error payload the model sees and can react to."""
    if name not in TOOL_REGISTRY:
        payload = {"error": f"Unknown tool '{name}'. Available: {list(TOOL_REGISTRY)}"}
        result.traces.append(TraceEvent(round_num, "error", {"tool": name, **payload}))
        return payload

    try:
        tool_result = TOOL_REGISTRY[name](**args)
        result.tools_consulted.append(name)
        result.traces.append(TraceEvent(round_num, "tool_result", {"tool": name, "args": args, "result": tool_result}))
        return {"result": tool_result}
    except Exception as e:  # noqa: BLE001 — deliberately broad: any tool failure must become a
        # visible function_response to the model, not an unhandled crash mid-loop
        payload = {"error": f"{type(e).__name__}: {e}"}
        result.traces.append(TraceEvent(round_num, "error", {"tool": name, "args": args, **payload}))
        return payload


def run_ops_agent(run_mode: str = "daily") -> OpsAgentRunResult:
    """Runs the agent loop end-to-end. Pure — does not touch the DB. See
    execute_and_save() for the persisted version.

    run_mode selects which single tool is offered this run (daily->headcount,
    weekly->churn, monthly->complaint) via tools.get_active_tools(). Raises
    ValueError up front for an unknown run_mode rather than silently running
    with zero lookup tools."""
    active_tools = get_active_tools(run_mode)  # raises ValueError if run_mode is bad
    tool_names = [t.name for t in active_tools]

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    result = OpsAgentRunResult()

    config = types.GenerateContentConfig(
        system_instruction=_build_system_prompt(run_mode, tool_names),
        tools=[types.Tool(function_declarations=active_tools + [SUBMIT_DECISION_TOOL])],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"Run today's ops review. Today's date is {date.today().isoformat()}.")],
        )
    ]

    any_tool_attempted = False  # True once a real tool has been CALLED, success or fail —
    # deliberately separate from result.tools_consulted (successes only). Blocks the
    # degenerate "finalize with zero effort" case while still allowing the legitimate
    # graceful-degradation case (every tool failed, model honestly reports that) to
    # reach submit_decision — that path is real and was observed in production.

    for round_num in range(1, MAX_ROUNDS + 1):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=contents, config=config)
        except Exception as e:  # noqa: BLE001 — API/network failure ends the run, not the process
            result.status = "error"
            result.error = f"Gemini API call failed on round {round_num}: {type(e).__name__}: {e}"
            result.traces.append(TraceEvent(round_num, "error", {"detail": result.error}))
            return result

        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            result.traces.append(TraceEvent(round_num, "error", {"detail": "empty response from model"}))
            continue  # counts against MAX_ROUNDS — malformed response, not a crash

        model_content = candidate.content
        contents.append(model_content)

        function_calls = [p.function_call for p in (model_content.parts or []) if p.function_call]
        text_parts = [p.text for p in (model_content.parts or []) if p.text]

        result.traces.append(TraceEvent(round_num, "model_response", {
            "text": " ".join(text_parts) if text_parts else None,
            "function_calls": [{"name": fc.name, "args": dict(fc.args or {})} for fc in function_calls],
        }))

        if not function_calls:
            # Nudge once instead of silently ending the run — lists only the
            # tool(s) actually active this run_mode, not a hardcoded pair.
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(
                    text=f"Call a tool ({' / '.join(tool_names)}) or, if you've "
                         "already checked what's relevant, call submit_decision to finish."
                )],
            ))
            continue

        response_parts: list[types.Part] = []
        finalized = False

        for fc in function_calls:
            args = dict(fc.args or {})
            result.traces.append(TraceEvent(round_num, "tool_call", {"tool": fc.name, "args": args}))

            if fc.name == "submit_decision":
                if not any_tool_attempted:
                    result.traces.append(TraceEvent(round_num, "error", {
                        "tool": fc.name, "detail": "submit_decision called before any lookup tool was attempted",
                    }))
                    response_parts.append(types.Part.from_function_response(
                        name=fc.name,
                        response={"error": f"Call {' or '.join(tool_names)} first — "
                                            "you haven't checked anything yet this run."},
                    ))
                    continue
                try:
                    args.setdefault("run_date", date.today().isoformat())
                    decision = OpsAgentDecision.model_validate(args)
                    decision.tools_consulted = sorted(set(result.tools_consulted))
                    result.decision = decision
                    result.status = "completed"
                    finalized = True
                    response_parts.append(types.Part.from_function_response(
                        name=fc.name, response={"result": "accepted"}
                    ))
                except ValidationError as e:
                    result.traces.append(TraceEvent(round_num, "error", {"tool": fc.name, "validation_error": str(e)}))
                    response_parts.append(types.Part.from_function_response(
                        name=fc.name,
                        response={"error": f"Validation failed, fix and re-call submit_decision: {e}"},
                    ))
            else:
                any_tool_attempted = True
                tool_response = _run_tool_call(fc.name, args, result, round_num)
                response_parts.append(types.Part.from_function_response(name=fc.name, response=tool_response))

        if finalized:
            return result

        contents.append(types.Content(role="user", parts=response_parts))

    # Ran out of rounds without a validated submit_decision
    if result.status != "completed":
        result.status = "incomplete"
        result.error = result.error or f"Did not finalize within {MAX_ROUNDS} rounds"
    return result


def execute_and_save(db: Session | None = None, run_mode: str | None = None) -> "AgentRun":  # noqa: F821
    """Runs the agent and persists agent_runs / agent_actions / agent_traces.
    Import of AgentRun/AgentAction/AgentTrace is local to avoid a hard
    dependency on the DB models for callers that only want run_ops_agent().

    run_mode: "daily" | "weekly" | "monthly". If not passed explicitly,
    read from the RUN_MODE env var (set by the calling GitHub Actions
    workflow), defaulting to "daily" if that's unset too — so existing
    callers that don't pass run_mode at all keep behaving like the old
    daily-only setup did.

    No agent_runs schema change needed to know which mode a given run was:
    result.tools_consulted (saved below) already names the one tool that
    ran, which uniquely identifies the mode via tools.TOOL_CADENCE.
    """
    run_mode = run_mode or os.environ.get("RUN_MODE", "daily")
    from app.models.models import AgentRun, AgentAction, AgentTrace, User  # local import, see docstring

    owns_session = db is None
    db = db or SessionLocal()
    try:
        result = run_ops_agent(run_mode)

        # related_user_id comes from the model, based on what get_churn_risk returned
        # earlier in the SAME run — normally trustworthy, but an LLM can misremember an
        # ID across rounds. A bad FK reference here would fail the single commit() below
        # and silently lose every action AND every trace from an otherwise-good run, not
        # just the one bad action. Check against real users up front instead.
        referenced_ids = {a.related_user_id for a in (result.decision.actions if result.decision else [])
                           if a.related_user_id is not None}
        valid_ids = set()
        if referenced_ids:
            valid_ids = {row[0] for row in db.query(User.id).filter(User.id.in_(referenced_ids)).all()}

        run = AgentRun(
            run_date=date.today(),
            status=result.status,
            summary=result.decision.summary if result.decision else None,
            tools_consulted=json.dumps(result.tools_consulted),
            error=result.error,
        )
        db.add(run)
        db.flush()  # get run.id before children reference it

        if result.decision:
            for action in result.decision.actions:
                related_user_id = action.related_user_id
                if related_user_id is not None and related_user_id not in valid_ids:
                    finalize_round = result.traces[-1].round_num if result.traces else 1
                    result.traces.append(TraceEvent(finalize_round, "error", {
                        "detail": f"submit_decision referenced related_user_id={related_user_id}, "
                                  f"which doesn't exist — dropped from the saved action rather than "
                                  f"failing the whole run",
                    }))
                    related_user_id = None
                db.add(AgentAction(
                    run_id=run.id,
                    category=action.category.value,
                    priority=action.priority.value,
                    summary=action.summary,
                    reasoning=action.reasoning,
                    drafted_message=action.drafted_message,
                    related_user_id=related_user_id,
                    related_date=action.related_date,
                    approval_status="pending",
                ))

        for trace in result.traces:
            db.add(AgentTrace(
                run_id=run.id,
                round_num=trace.round_num,
                event_type=trace.event_type,
                detail=json.dumps(trace.detail, default=str),
                created_at=trace.timestamp,
            ))

        db.commit()
        db.refresh(run)
        return run
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    # Manual test run — does NOT write to the DB, just prints what the
    # agent decided. Reads RUN_MODE from env (defaults to "daily"), same
    # as execute_and_save() does — e.g. `set RUN_MODE=weekly` first on
    # Windows CMD, or `$env:RUN_MODE="weekly"` in PowerShell.
    outcome = run_ops_agent(os.environ.get("RUN_MODE", "daily"))
    print(f"Status: {outcome.status}")
    if outcome.error:
        print(f"Error: {outcome.error}")
    print(f"Tools consulted: {outcome.tools_consulted}")
    if outcome.decision:
        print("\nDecision:")
        print(outcome.decision.model_dump_json(indent=2))
    print(f"\n{len(outcome.traces)} trace events:")
    for t in outcome.traces:
        print(f"  round {t.round_num} | {t.event_type} | {json.dumps(t.detail, default=str)[:200]}")