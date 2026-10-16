from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.assistant.loop import resume_pending_confirmation, run_assistant
from app.auth import require_student
from app.models.core import User


router = APIRouter(
    prefix="/assistant",
    tags=["Assistant"],
)


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation: list[dict] = Field(default_factory=list)


class AssistantConfirmRequest(BaseModel):
    pending_id: str = Field(min_length=1, max_length=100)
    approve: bool


@router.post("/chat")
def assistant_chat(
    request: AssistantChatRequest,
    user: User = Depends(require_student),
):
    """
    Send a message to the assistant. The student comes from the JWT.

    If the response has status "pending_confirmation", show the label
    with Yes/No buttons and call POST /assistant/confirm.
    """
    return run_assistant(
        user_message=request.message,
        conversation=request.conversation,
        student_id=user.id,
    )


@router.post("/confirm")
def assistant_confirm(
    request: AssistantConfirmRequest,
    user: User = Depends(require_student),
):
    """Answer a pending save with Yes (approve=true) or No."""
    result = resume_pending_confirmation(
        pending_id=request.pending_id,
        approve=request.approve,
        student_id=user.id,
    )

    if result["status"] == "invalid_pending":
        raise HTTPException(status_code=404, detail=result["answer"])

    if result["status"] == "forbidden":
        raise HTTPException(status_code=403, detail=result["answer"])

    return result
