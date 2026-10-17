"""Persistent, student-bound, single-use approvals. No model-controlled execution."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, BigInteger, select, update
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import BIGINT

from app.database import Base
from app.models.core import Student, Job
from app.models.additional import Event, SavedItem


class PendingAction(Base):
    __tablename__ = 'assistant_pending_actions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[int] = mapped_column(BigInteger().with_variant(BIGINT(unsigned=True), 'mysql'), ForeignKey('students.user_id', ondelete='CASCADE'), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False)
    conversation: Mapped[list] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SaveArguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    job_id: int | None = Field(default=None, gt=0)
    event_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def one_target(self):
        if (self.job_id is None) == (self.event_id is None):
            raise ValueError('Provide exactly one job_id or event_id')
        return self


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def validate_target(db, student_id, arguments):
    if db.get(Student, student_id) is None:
        raise HTTPException(409, 'Create your student profile before saving opportunities.')
    values = {k: v for k, v in arguments.items() if k not in ('confirmed', 'student_id')}
    try:
        action = SaveArguments.model_validate(values)
    except ValidationError:
        raise HTTPException(422, 'Save requires exactly one valid job or event ID.')
    kind, model, target = ('job', Job, action.job_id) if action.job_id else ('event', Event, action.event_id)
    row = db.get(model, target)
    if row is None:
        raise HTTPException(404, f'{kind.title()} not found.')
    title = row.title if kind == 'job' else row.event_name
    return action.model_dump(exclude_none=True), f'Save {kind} “{title}” (ID {target}) to your saved items?'


def create_pending(db, student_id, arguments, conversation, explanation):
    token = secrets.token_urlsafe(32)
    db.add(PendingAction(id=token_hash(token), student_id=student_id, arguments=arguments,
                         conversation=conversation, expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)))
    db.commit()
    return dict(answer=explanation, status='pending_confirmation', pending_id=token,
                conversation=conversation, expires_in_seconds=600)


def resolve_pending(db, student_id, pending_id, approve):
    claimed = db.execute(update(PendingAction).where(
        PendingAction.id == token_hash(pending_id), PendingAction.student_id == student_id,
        PendingAction.consumed.is_(False), PendingAction.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
    ).values(consumed=True).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Confirmation is invalid, expired, or already used.')
    pending = db.get(PendingAction, token_hash(pending_id), populate_existing=True)
    if approve:
        arguments, _ = validate_target(db, student_id, pending.arguments)
        query = select(SavedItem).where(SavedItem.student_id == student_id)
        for key, value in arguments.items():
            query = query.where(getattr(SavedItem, key) == value)
        if db.scalar(query) is None:
            db.add(SavedItem(student_id=student_id, **arguments))
            answer = 'Saved to your items after your approval.'
        else:
            answer = 'This opportunity is already in your saved items.'
        status = 'completed'
    else:
        answer, status = 'Cancelled. Nothing was saved.', 'cancelled'
    conversation = pending.conversation + [
        {'role': 'user', 'content': 'Yes, approve this save.' if approve else 'No, cancel this save.'},
        {'role': 'assistant', 'content': answer},
    ]
    db.commit()
    return dict(answer=answer, status=status, conversation=conversation, tool_calls=0, iterations=0)
