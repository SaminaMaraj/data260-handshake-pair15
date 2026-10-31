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

from services.assistant import memory
from services.assistant.agent.loop import resume_pending_confirmation, run_assistant
from services.common.auth import CurrentUser, require_student
from services.common.mongo import database, log_activity

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

    if memory.is_memory_command(request.message):
        result = memory.handle_memory_command(db, user.id, request.message)
        conversation = conversation + [{"role": "user", "content": request.message},
                                       {"role": "assistant", "content": result["answer"]}]
        result.update({"status": "completed", "tool_calls": 0, "iterations": 0,
                       "failures": [], "conversation": conversation, "command": "memory"})
    else:
        result = run_assistant(user_message=request.message, conversation=conversation,
                               student_id=user.id)

    memory.save_session(db, session_id, user.id, result["conversation"])
    result["session_id"] = session_id
    log_activity(db, user.id, "assistant_chat", status=result.get("status"),
                 tool_calls=result.get("tool_calls"), session_id=session_id)
    return result


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
