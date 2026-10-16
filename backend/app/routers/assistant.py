from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.assistant.loop import run_assistant


router = APIRouter(
    prefix="/assistant",
    tags=["Assistant"],
)


class AssistantChatRequest(BaseModel):
    message: str
    student_id: int = 1
    conversation: list[dict] = Field(default_factory=list)


@router.post("/chat")
def assistant_chat(request: AssistantChatRequest):
    return run_assistant(
        user_message=request.message,
        conversation=request.conversation,
        student_id=request.student_id,
    )