from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.additional import Application, Resume
from app.models.core import Job, Student
from app.schemas import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
)


router = APIRouter(
    prefix="/applications",
    tags=["Applications"],
)


@router.post("", response_model=ApplicationRead, status_code=201)
def create_application(
    application_data: ApplicationCreate,
    db: Session = Depends(get_db),
):
    job = db.get(Job, application_data.job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    student = db.get(Student, application_data.student_id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    resume = db.get(Resume, application_data.resume_id)

    if resume is None:
        raise HTTPException(
            status_code=404,
            detail="Resume not found",
        )

    if resume.student_id != student.user_id:
        raise HTTPException(
            status_code=400,
            detail="Resume does not belong to this student",
        )

    existing_application = db.scalar(
        select(Application).where(
            Application.job_id == application_data.job_id,
            Application.student_id == application_data.student_id,
        )
    )

    if existing_application is not None:
        raise HTTPException(
            status_code=409,
            detail="Student has already applied for this job",
        )

    application = Application(
        job_id=application_data.job_id,
        student_id=application_data.student_id,
        resume_id=application_data.resume_id,
    )

    db.add(application)
    db.commit()
    db.refresh(application)

    return application


@router.patch(
    "/{application_id}/status",
    response_model=ApplicationRead,
)
def update_application_status(
    application_id: int,
    status_data: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
):
    application = db.get(Application, application_id)

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    application.status = status_data.status

    if status_data.status == "pending":
        application.reviewed_at = None
    else:
        application.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(application)

    return application


@router.get(
    "/student/{student_id}",
    response_model=list[ApplicationRead],
)
def list_student_applications(
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
        select(Application)
        .where(Application.student_id == student_id)
        .order_by(Application.id.desc())
    )

    return db.scalars(statement).all()


@router.get(
    "/{application_id}",
    response_model=ApplicationRead,
)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
):
    application = db.get(Application, application_id)

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    return application