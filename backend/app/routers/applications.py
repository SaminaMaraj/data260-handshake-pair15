
"""Application routes combining student security and application history."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_student
from app.database import get_db
from app.models.additional import Application, Resume
from app.models.core import Company, Job, Student, User
from app.schemas import ApplicationCreate, ApplicationRead, ResumeOption

router = APIRouter(tags=["Applications"])


def application_query():
    return (
        select(
            Application.id,
            Application.job_id,
            Application.student_id,
            Application.resume_id,
            Application.status,
            Application.applied_at,
            Application.reviewed_at,
            Job.title.label("job_title"),
            Job.company_id,
            Company.company_name,
            Student.full_name.label("student_name"),
        )
        .join(Job, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.user_id)
        .join(Student, Application.student_id == Student.user_id)
    )


@router.get("/applications", response_model=list[ApplicationRead])
def my_applications(
    status: Literal["pending", "reviewed", "declined"] | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    stmt = application_query().where(Application.student_id == user.id)

    if status:
        stmt = stmt.where(Application.status == status)

    return db.execute(
        stmt.order_by(Application.applied_at.desc(), Application.id.desc())
    ).mappings().all()


@router.get(
    "/applications/resume-options",
    response_model=list[ResumeOption],
)
def resume_options(
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    return db.scalars(
        select(Resume)
        .where(Resume.student_id == user.id)
        .order_by(Resume.id.desc())
    ).all()


@router.post(
    "/applications",
    response_model=ApplicationRead,
    status_code=201,
)
def apply_to_job(
    data: ApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    job = db.get(Job, data.job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.deadline < date.today():
        raise HTTPException(
            status_code=409,
            detail="The application deadline has passed.",
        )

    if db.get(Student, user.id) is None:
        raise HTTPException(
            status_code=409,
            detail="Create your student profile before applying.",
        )

    existing = db.scalar(
        select(Application.id).where(
            Application.job_id == data.job_id,
            Application.student_id == user.id,
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="You have already applied to this job.",
        )

    resume = db.get(Resume, data.resume_id)

    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")

    if resume.student_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only use your own resume.",
        )

    application = Application(
        job_id=data.job_id,
        student_id=user.id,
        resume_id=resume.id,
    )

    db.add(application)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()

        if getattr(error.orig, "args", (None,))[0] == 1062:
            raise HTTPException(
                status_code=409,
                detail="You have already applied to this job.",
            )

        raise HTTPException(
            status_code=409,
            detail="Application could not be saved. Refresh and try again.",
        )

    db.refresh(application)

    return db.execute(
        application_query().where(Application.id == application.id)
    ).mappings().one()


@router.get(
    "/applications/student/{student_id}",
    response_model=list[ApplicationRead],
)
def list_student_applications(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    if student_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only view your own applications.",
        )

    student = db.get(Student, student_id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    stmt = application_query().where(
        Application.student_id == student_id
    )

    return db.execute(
        stmt.order_by(Application.id.desc())
    ).mappings().all()


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationRead,
)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    application = db.get(Application, application_id)

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    if application.student_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only view your own applications.",
        )

    return db.execute(
        application_query().where(Application.id == application_id)
    ).mappings().one()
