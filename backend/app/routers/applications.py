"""Student-owned applications and existing-resume choices; no upload endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_student
from app.database import get_db
from app.models.core import Company, Job, Student, User
from app.models.additional import Application, Resume
from app.schemas import ApplicationCreate, ApplicationRead, ResumeOption

router = APIRouter()


def application_query():
    return select(
        Application.id, Application.job_id, Application.student_id,
        Application.resume_id, Application.status, Application.applied_at,
        Application.reviewed_at, Job.title.label("job_title"),
        Job.company_id, Company.company_name,
    ).join(Job, Application.job_id == Job.id).join(Company, Job.company_id == Company.user_id)


@router.get("/applications", response_model=list[ApplicationRead])
def my_applications(db: Session = Depends(get_db), user: User = Depends(require_student)):
    return db.execute(application_query().where(Application.student_id == user.id)
                      .order_by(Application.applied_at.desc(), Application.id.desc())).mappings().all()


@router.get("/applications/resume-options", response_model=list[ResumeOption])
def resume_options(db: Session = Depends(get_db), user: User = Depends(require_student)):
    return db.scalars(select(Resume).where(Resume.student_id == user.id).order_by(Resume.id.desc())).all()


@router.post("/applications", response_model=ApplicationRead, status_code=201)
def apply_to_job(data: ApplicationCreate, db: Session = Depends(get_db),
                 user: User = Depends(require_student)):
    if db.get(Job, data.job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if db.get(Student, user.id) is None:
        raise HTTPException(status_code=409, detail="Create your student profile before applying.")
    if db.scalar(select(Application.id).where(
        Application.job_id == data.job_id, Application.student_id == user.id,
    )) is not None:
        raise HTTPException(status_code=409, detail="You have already applied to this job.")
    resume = db.get(Resume, data.resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    if resume.student_id != user.id:
        raise HTTPException(status_code=403, detail="You can only use your own resume.")
    application = Application(job_id=data.job_id, student_id=user.id, resume_id=resume.id)
    db.add(application)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # The existing database unique key also protects simultaneous submissions.
        if getattr(error.orig, "args", (None,))[0] == 1062:
            raise HTTPException(status_code=409, detail="You have already applied to this job.")
        raise HTTPException(status_code=409, detail="Application could not be saved. Refresh and try again.")
    db.refresh(application)
    return db.execute(application_query().where(Application.id == application.id)).mappings().one()
