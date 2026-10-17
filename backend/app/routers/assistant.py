import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.orm import Session

from app.auth import require_student
from app.database import get_db
from app.models.core import User
from app.assistant.loop import run_assistant
from app.assistant.pending import resolve_pending

router = APIRouter(prefix='/assistant', tags=['Assistant'])


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    student_id: int | None = None  # Legacy shape accepted, never used for identity.
    conversation: list[dict] = Field(default_factory=list, max_length=200)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pending_id: str = Field(min_length=1, max_length=128)
    approve: StrictBool


@router.post('/chat')
def assistant_chat(request: AssistantChatRequest, db: Session = Depends(get_db),
                   user: User = Depends(require_student)):
    if not request.message.strip():
        raise HTTPException(422, 'Message must not be blank.')
    if len(json.dumps(request.conversation).encode()) > 256_000:
        raise HTTPException(422, 'Conversation is too long. Please clear it and start again.')
    for message in request.conversation:
        if message.get('role') not in ('user', 'assistant', 'tool') or not isinstance(message.get('content', ''), str):
            raise HTTPException(422, 'Invalid conversation message.')
    return run_assistant(user_message=request.message, conversation=request.conversation,
                         student_id=user.id, db=db)


@router.post('/confirm')
def assistant_confirm(request: ConfirmRequest, db: Session = Depends(get_db),
                      user: User = Depends(require_student)):
    try:
        return resolve_pending(db, user.id, request.pending_id, request.approve)
    except Exception:
        db.rollback()
        raise
