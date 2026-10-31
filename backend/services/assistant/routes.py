"""p15-assistant routes: the hand-built agent loop over MongoDB-backed tools.

The student always comes from the JWT; the frontend never supplies it.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.assistant.agent.loop import resume_pending_confirmation, run_assistant
from services.common.auth import CurrentUser, require_student
from services.common.mongo import database, log_activity

router = APIRouter(prefix="/assistant", tags=["Assistant"])


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation: list[dict] = Field(default_factory=list)


class AssistantConfirmRequest(BaseModel):
    pending_id: str = Field(min_length=1, max_length=100)
    approve: bool


@router.post("/chat")
def assistant_chat(request: AssistantChatRequest,
                   user: CurrentUser = Depends(require_student)):
    """Send a message to the assistant.

    If the response has status "pending_confirmation", show the label with
    Yes/No buttons and call POST /assistant/confirm.
    """
    result = run_assistant(user_message=request.message,
                           conversation=request.conversation, student_id=user.id)
    log_activity(database(), user.id, "assistant_chat", status=result.get("status"),
                 tool_calls=result.get("tool_calls"))
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
    log_activity(database(), user.id, "assistant_confirm", approve=request.approve,
                 status=result.get("status"))
    return result
