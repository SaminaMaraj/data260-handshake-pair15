from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.auth import get_current_user, require_student
from app.database import get_db
from app.routers.part_a import event_output
from app.models.additional import Event, EventRegistration
from app.models.core import Student, User
from app.schemas import (
    EventRead,
    EventRegistrationCreate,
    EventRegistrationRead,
)

router = APIRouter(tags=["Events"])


@router.get("/events/search", response_model=list[EventRead])
def search_events(
    q: str | None = None,
    location: str | None = None,
    from_date: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = select(Event)

    if q:
        search_text = f"%{q}%"
        statement = statement.where(
            or_(
                Event.event_name.ilike(search_text),
                Event.description.ilike(search_text),
                Event.eligibility.ilike(search_text),
            )
        )

    if location:
        statement = statement.where(
            Event.location.ilike(f"%{location}%")
        )

    if from_date:
        statement = statement.where(Event.event_date >= from_date)

    statement = statement.order_by(Event.event_date.asc())

    return db.scalars(statement).all()


@router.post(
    "/event-registrations",
    response_model=EventRegistrationRead,
    status_code=201,
)
def register_for_event(
    registration_data: EventRegistrationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    if registration_data.student_id != user.id:
        raise HTTPException(403, "You can only register yourself for an event")
    event = db.get(Event, registration_data.event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    student = db.get(Student, registration_data.student_id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    existing_registration = db.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == registration_data.event_id,
            EventRegistration.student_id == registration_data.student_id,
        )
    )

    if existing_registration is not None:
        raise HTTPException(
            status_code=409,
            detail="Student is already registered for this event",
        )

    # Keep the legacy request/response shape, but enforce Part A eligibility
    # and the registration deadline on this entry point too.
    output = event_output(event, db, user)
    if not output["eligible"]:
        raise HTTPException(403, output["ineligible_reason"])

    registration = EventRegistration(
        event_id=registration_data.event_id,
        student_id=registration_data.student_id,
    )

    db.add(registration)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Event registration could not be saved")
    db.refresh(registration)

    return registration


@router.get(
    "/event-registrations/student/{student_id}",
    response_model=list[EventRegistrationRead],
)
def list_student_event_registrations(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    if student_id != user.id:
        raise HTTPException(403, "You can only view your own registration history")
    student = db.get(Student, student_id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    statement = (
        select(EventRegistration)
        .where(EventRegistration.student_id == student_id)
        .order_by(EventRegistration.id.desc())
    )

    return db.scalars(statement).all()


@router.get(
    "/event-registrations/{registration_id}",
    response_model=EventRegistrationRead,
)
def get_event_registration(
    registration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    registration = db.get(EventRegistration, registration_id)

    if registration is None:
        raise HTTPException(
            status_code=404,
            detail="Event registration not found",
        )

    event = db.get(Event, registration.event_id)
    owns_registration = user.role == "student" and registration.student_id == user.id
    owns_event = user.role == "company" and event is not None and event.company_id == user.id
    if not (owns_registration or owns_event):
        raise HTTPException(403, "This registration is not available to your account")

    return registration
