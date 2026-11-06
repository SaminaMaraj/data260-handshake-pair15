"""p15-assistant routes: the hand-built agent loop with three-layer memory.

The student always comes from the JWT; the frontend never supplies it.

Sessions (memory layer 3): the first /assistant/chat returns a session_id;
send it back on later turns and the server uses its stored copy of the
conversation. POST /assistant/session/end hands the conversation to the
consolidation consumer over Kafka. Clients that still send only
`conversation` (Lab 1 style) keep working.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.assistant import compaction, memory
from services.assistant.agent.loop import (
    CONTEXT_WINDOW, resume_pending_confirmation, run_assistant)
from services.common import tracing
from services.common.auth import CurrentUser, require_student
from services.common.mongo import CONVERSATIONS, database, log_activity, utcnow

router = APIRouter(prefix="/assistant", tags=["Assistant"])


def on_startup():
    memory.seed_rules(database())


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation: list[dict] = Field(default_factory=list)
    session_id: str | None = Field(default=None, max_length=64)


class AssistantConfirmRequest(BaseModel):
    pending_id: str = Field(min_length=1, max_length=100)
    approve: bool
    session_id: str | None = Field(default=None, max_length=64)


class SessionEndRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)


def _conversation_for(db, request, user) -> tuple[str, list[dict]]:
    if request.session_id:
        session = memory.load_session(db, request.session_id, user.id)
        if session is None:
            raise HTTPException(404, "Assistant session not found or already ended")
        return request.session_id, session.get("messages", [])
    return secrets.token_urlsafe(16), request.conversation


@router.post("/chat")
def assistant_chat(request: AssistantChatRequest,
                   user: CurrentUser = Depends(require_student)):
    """Send a message to the assistant.

    If the response has status "pending_confirmation", show the label with
    Yes/No buttons and call POST /assistant/confirm. Messages starting with
    /memory are answered by code (see services/assistant/memory.py).
    """
    db = database()
    session_id, conversation = _conversation_for(db, request, user)
    text = request.message.strip()

    if memory.is_memory_command(text):
        result = memory.handle_memory_command(db, user.id, text)
        result.update(_command_result(conversation, text, result["answer"], "memory"))
    elif text.lower() in ("/compact", "/compact now"):
        compacted, report = compaction.compact(db, user.id, conversation, text,
                                               session_id=session_id, reason="command")
        if report.get("skipped"):
            answer = (f"Nothing to compact: this session uses about {report['tokens_before']} "
                      f"tokens ({report['context_pct_before']}% of the context window), and a "
                      "summary would not be smaller.")
        else:
            answer = (f"Compacted this session: about {report['tokens_before']} -> "
                      f"{report['tokens_after']} tokens ({report['context_pct_before']}% -> "
                      f"{report['context_pct_after']}% of the context window). I kept your "
                      "preferences, the jobs, companies and events we looked at, your "
                      "applications, and your latest search.")
        result = {"answer": answer, "compaction": report,
                  **_command_result(compacted, None, None, "compact")}
    else:
        result = run_assistant(user_message=request.message, conversation=conversation,
                               student_id=user.id)
        # Recorded before any compaction, which replaces this turn's messages.
        result["tools_used"] = _turn_tools(result.get("conversation") or [], len(conversation))
        # Automatic compaction once the session uses most of the context window.
        if result.get("tokens", {}).get("context_pct", 0) >= compaction.COMPACT_THRESHOLD_PCT \
                and result.get("status") == "completed":
            compacted, report = compaction.compact(db, user.id, result["conversation"],
                                                   request.message, session_id=session_id,
                                                   reason="threshold")
            if report.get("skipped"):
                result["compaction"] = report
            else:
                result["conversation"], result["compaction"] = compacted, report

    memory.save_session(db, session_id, user.id, result["conversation"])
    _record_tokens(db, user.id, session_id, result)  # after the session document exists
    result["session_id"] = session_id
    log_activity(db, user.id, "assistant_chat", status=result.get("status"),
                 tool_calls=result.get("tool_calls"), session_id=session_id)
    return result


def _turn_tools(conversation: list[dict], start: int) -> list[str]:
    """Names of the tools the model called in this turn, in order."""
    return [tc["function"]["name"] for m in conversation[start:] if m.get("role") == "assistant"
            for tc in m.get("tool_calls") or []]


def _command_result(conversation, text, answer, command) -> dict:
    """Shape of a command reply (no model call)."""
    if text is not None:
        conversation = conversation + [{"role": "user", "content": text},
                                       {"role": "assistant", "content": answer}]
    return {"status": "completed", "tool_calls": 0, "iterations": 0, "failures": [],
            "guardrails": [], "conversation": conversation, "command": command,
            "trace_id": tracing.current_trace_id(),
            "tokens": {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                       "total_tokens": 0, "context_used": 0, "context_window": CONTEXT_WINDOW,
                       "context_pct": 0.0, "warning": False, "estimated": False, "calls": []}}


def _record_tokens(db, student_id, session_id, result) -> None:
    """Token usage after every model call (token_usage) and per session."""
    tokens = result.get("tokens") or {}
    if not tokens.get("model_calls"):
        return
    now = utcnow()
    db["token_usage"].insert_many([
        {"student_id": student_id, "session_id": session_id, "trace_id": result.get("trace_id"),
         "at": now, "context_window": tokens["context_window"],
         "estimated": tokens["estimated"], **call} for call in tokens["calls"]])
    db[CONVERSATIONS].update_one(
        {"_id": session_id, "student_id": student_id},
        {"$inc": {"tokens_total": tokens["total_tokens"]},
         "$set": {"last_context_pct": tokens["context_pct"]}})


@router.post("/confirm")
def assistant_confirm(request: AssistantConfirmRequest,
                      user: CurrentUser = Depends(require_student)):
    """Answer a pending save with Yes (approve=true) or No."""
    result = resume_pending_confirmation(pending_id=request.pending_id,
                                         approve=request.approve, student_id=user.id)
    if result["status"] == "invalid_pending":
        raise HTTPException(status_code=404, detail=result["answer"])
    if result["status"] == "forbidden":
        raise HTTPException(status_code=403, detail=result["answer"])
    db = database()
    if request.session_id and memory.load_session(db, request.session_id, user.id):
        memory.save_session(db, request.session_id, user.id, result["conversation"])
        result["session_id"] = request.session_id
    log_activity(db, user.id, "assistant_confirm", approve=request.approve,
                 status=result.get("status"))
    return result


@router.post("/session/end")
def end_session(request: SessionEndRequest, user: CurrentUser = Depends(require_student)):
    """End the session: the consolidation consumer extracts lasting facts
    into learned memory, then discards the conversation."""
    result = memory.end_session(database(), request.session_id, user.id)
    if result["status"] == "not_found":
        raise HTTPException(404, "Assistant session not found or already ended")
    return result


@router.get("/memory")
def get_memory(user: CurrentUser = Depends(require_student)):
    """The signed-in student's learned memory, one line per entry."""
    entries = memory.list_entries(database(), user.id)
    return {"student_id": user.id, "count": len(entries),
            "entries": [memory.render_line(e) for e in entries]}
