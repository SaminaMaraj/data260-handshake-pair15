from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_student
from app.database import get_db
from app.models.additional import Event, SavedItem, StudentPreference
from app.models.core import Job, Student, User
from app.schemas import (
    SavedItemCreate,
    SavedItemRead,
    StudentPreferenceCreate,
    StudentPreferenceRead,
)

router = APIRouter(tags=["Preferences and Saved Items"])


def _require_same_student(student_id: int, user: User) -> None:
    """Reject requests that name a different student than the JWT."""
    if student_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own data",
        )


@router.put(
    "/students/{student_id}/preferences",
    response_model=StudentPreferenceRead,
)
def save_student_preferences(
    student_id: int,
    preference_data: StudentPreferenceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    _require_same_student(student_id, user)

    student = db.get(Student, user.id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    preference = db.get(StudentPreference, user.id)

    if preference is None:
        preference = StudentPreference(
            student_id=user.id,
            **preference_data.model_dump(),
        )
        db.add(preference)
    else:
        for field, value in preference_data.model_dump().items():
            setattr(preference, field, value)

    db.commit()
    db.refresh(preference)

    return preference


@router.get(
    "/students/{student_id}/preferences",
    response_model=StudentPreferenceRead,
)
def get_student_preferences(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    _require_same_student(student_id, user)

    preference = db.get(StudentPreference, user.id)

    if preference is None:
        raise HTTPException(
            status_code=404,
            detail="No preferences saved for this student",
        )

    return preference


@router.post(
    "/saved-items",
    response_model=SavedItemRead,
    status_code=201,
)
def save_item(
    saved_item_data: SavedItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    # The body still carries student_id for compatibility, but the
    # saved item always belongs to the authenticated student.
    _require_same_student(saved_item_data.student_id, user)

    has_job = saved_item_data.job_id is not None
    has_event = saved_item_data.event_id is not None

    if has_job == has_event:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of job_id or event_id",
        )

    student = db.get(Student, user.id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    if saved_item_data.job_id is not None:
        if db.get(Job, saved_item_data.job_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Job not found",
            )

        existing_item = db.scalar(
            select(SavedItem).where(
                SavedItem.student_id == user.id,
                SavedItem.job_id == saved_item_data.job_id,
            )
        )
    else:
        if db.get(Event, saved_item_data.event_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Event not found",
            )

        existing_item = db.scalar(
            select(SavedItem).where(
                SavedItem.student_id == user.id,
                SavedItem.event_id == saved_item_data.event_id,
            )
        )

    if existing_item is not None:
        raise HTTPException(
            status_code=409,
            detail="This item is already saved",
        )

    saved_item = SavedItem(
        student_id=user.id,
        job_id=saved_item_data.job_id,
        event_id=saved_item_data.event_id,
    )

    db.add(saved_item)
    db.commit()
    db.refresh(saved_item)

    return saved_item


@router.get(
    "/saved-items/student/{student_id}",
    response_model=list[SavedItemRead],
)
def list_saved_items(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    _require_same_student(student_id, user)

    student = db.get(Student, user.id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    statement = (
        select(SavedItem)
        .where(SavedItem.student_id == user.id)
        .order_by(SavedItem.id.desc())
    )

    return db.scalars(statement).all()


@router.delete(
    "/saved-items/{saved_item_id}",
    status_code=204,
)
def delete_saved_item(
    saved_item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    saved_item = db.get(SavedItem, saved_item_id)

    if saved_item is None:
        raise HTTPException(
            status_code=404,
            detail="Saved item not found",
        )

    if saved_item.student_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own saved items",
        )

    db.delete(saved_item)
    db.commit()

    return None
