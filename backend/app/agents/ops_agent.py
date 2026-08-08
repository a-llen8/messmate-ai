"""
MessMate — Caterer Ops Agent loop controller.

This is a real agent loop, not a fixed pipeline: each round, Gemini sees
the conversation so far (including every prior tool result) and decides
for itself whether to call another tool or finalize, via a `submit_decision`
function call that IS the finalize action rather than a separate code path
— it goes through the same validate/retry machinery as any other tool call.

Currently wired with only get_churn_risk + get_headcount_forecast (see
tools.py — complaint cluster trend is parked). The system prompt below
only promises the tools actually in ACTIVE_TOOLS; when the complaint tool
is added, update the prompt too.

Run this directly for a manual test:
    cd backend
    venv\\Scripts\\activate
    python -m app.agents.ops_agent

Not yet wired to a scheduler. Doc's plan was Celery beat, daily — but
there's no celery app instance configured yet (app/celery/__init__.py is
empty) and the deployment story for a long-running worker is still
undecided (see project notes: college server vs. GitHub Actions cron).
execute_and_save() below is the entrypoint either path would call; wiring
the actual trigger is separate work, not done here.
"""

import json
from datetime import date, datetime

from google import genai
from google.genai import types
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.agents.tools import ACTIVE_TOOLS, TOOL_REGISTRY
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

SYSTEM_PROMPT = """You are the MessMate Caterer Ops Agent, running once daily.

Your job: review student churn risk and tomorrow's headcount forecast, and
decide what (if anything) the caterer should act on today. You have two
lookup tools and one finalize tool:

- get_churn_risk: at-risk students, scored today
- get_headcount_forecast: predicted headcount per meal slot for tomorrow
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
- You get up to a few rounds. Check the tools relevant to today, then call
  submit_decision. Don't call the same tool twice unless you have a real
  reason to (e.g. re-checking with a different date).
"""


class TraceEvent:
    """One row's worth of data for agent_traces — a single round's model
    output and/or tool call, kept separate from persistence so the loop
    itself doesn't need a live DB session to run (e.g. for local testing)."""

    def __init__(self, round_num: int, event_type: str, detail: dict):
        self.round_num = round_num
        self.event_type = event_type  # "model_response" | "tool_call" | "tool_result" | "error"
        self.detail = detail
        self.timestamp = datetime.utcnow()


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


def run_ops_agent() -> OpsAgentRunResult:
    """Runs the agent loop end-to-end. Pure — does not touch the DB. See
    execute_and_save() for the persisted version."""
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    result = OpsAgentRunResult()

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=ACTIVE_TOOLS + [SUBMIT_DECISION_TOOL])],
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
            # Nudge once instead of silently ending the run
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(
                    text="Call a tool (get_churn_risk / get_headcount_forecast) or, if you've "
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
                        response={"error": "Call get_churn_risk and/or get_headcount_forecast first — "
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


def execute_and_save(db: Session | None = None) -> "AgentRun":  # noqa: F821 — see app.models.models
    """Runs the agent and persists agent_runs / agent_actions / agent_traces.
    Import of AgentRun/AgentAction/AgentTrace is local to avoid a hard
    dependency on the DB models for callers that only want run_ops_agent()."""
    from app.models.models import AgentRun, AgentAction, AgentTrace, User  # local import, see docstring

    owns_session = db is None
    db = db or SessionLocal()
    try:
        result = run_ops_agent()

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
    # agent decided. Useful before wiring execute_and_save() into anything.
    outcome = run_ops_agent()
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