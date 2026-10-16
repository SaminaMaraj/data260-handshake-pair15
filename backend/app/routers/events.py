from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.additional import Event, EventRegistration
from app.models.core import Company, Student
from app.schemas import (
    EventCreate,
    EventRead,
    EventRegistrationCreate,
    EventRegistrationRead,
)


router = APIRouter(tags=["Events"])


@router.post("/events", response_model=EventRead, status_code=201)
def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db),
):
    company = db.get(Company, event_data.company_id)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    event = Event(**event_data.model_dump())

    db.add(event)
    db.commit()
    db.refresh(event)

    return event


@router.get("/events", response_model=list[EventRead])
def list_events(db: Session = Depends(get_db)):
    statement = select(Event).order_by(Event.event_date.asc())

    return db.scalars(statement).all()


@router.get("/events/{event_id}", response_model=EventRead)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    return event


@router.post(
    "/event-registrations",
    response_model=EventRegistrationRead,
    status_code=201,
)
def register_for_event(
    registration_data: EventRegistrationCreate,
    db: Session = Depends(get_db),
):
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

    registration = EventRegistration(
        event_id=registration_data.event_id,
        student_id=registration_data.student_id,
    )

    db.add(registration)
    db.commit()
    db.refresh(registration)

    return registration


@router.get(
    "/event-registrations/student/{student_id}",
    response_model=list[EventRegistrationRead],
)
def list_student_event_registrations(
    student_id: int,
    db: Session = Depends(get_db),
):
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
):
    registration = db.get(EventRegistration, registration_id)

    if registration is None:
        raise HTTPException(
            status_code=404,
            detail="Event registration not found",
        )

    return registration