"""p15-application routes on MongoDB: applying, history, and company review."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.schemas import ApplicationCreate, ApplicationRead, ResumeOption
from services.common import repo
from services.common.auth import CurrentUser, require_company, require_student
from services.common.mongo import JOBS, RESUMES, get_mongo
from services.common.repo import DomainError

router = APIRouter(tags=["Applications"])
Status = Literal["pending", "reviewed", "declined"]
NEWEST_FIRST = [("applied_at", -1), ("_id", -1)]

# Hooks for the Kafka producers (application.created / status_changed).
on_application_created = []
on_status_changed = []


@router.get("/applications", response_model=list[ApplicationRead])
def my_applications(status: Status | None = None, db=Depends(get_mongo),
                    user: CurrentUser = Depends(require_student)):
    query = {"student_id": user.id}
    if status:
        query["status"] = status
    return repo.application_rows(db, query, NEWEST_FIRST)


@router.get("/applications/resume-options", response_model=list[ResumeOption])
def resume_options(db=Depends(get_mongo), user: CurrentUser = Depends(require_student)):
    return [{"id": r["_id"], "original_filename": r["original_filename"]}
            for r in db[RESUMES].find({"student_id": user.id}).sort("_id", -1)]


@router.post("/applications", response_model=ApplicationRead, status_code=201)
def apply_to_job(data: ApplicationCreate, db=Depends(get_mongo),
                 user: CurrentUser = Depends(require_student)):
    try:
        row = repo.create_application(db, job_id=data.job_id, student_id=user.id,
                                      resume_id=data.resume_id)
    except DomainError as err:
        raise HTTPException(err.status, err.message)
    for hook in on_application_created:
        hook(row)
    return row


@router.get("/applications/student/{student_id}", response_model=list[ApplicationRead])
def list_student_applications(student_id: int, db=Depends(get_mongo),
                              user: CurrentUser = Depends(require_student)):
    if student_id != user.id:
        raise HTTPException(403, "You can only view your own applications.")
    if repo.get_student(db, student_id) is None:
        raise HTTPException(404, "Student not found")
    return repo.application_rows(db, {"student_id": student_id}, [("_id", -1)])


@router.get("/applications/{application_id}", response_model=ApplicationRead)
def get_application(application_id: int, db=Depends(get_mongo),
                    user: CurrentUser = Depends(require_student)):
    row = repo.application_row(db, application_id)
    if row is None:
        raise HTTPException(404, "Application not found")
    if row["student_id"] != user.id:
        raise HTTPException(403, "You can only view your own applications.")
    return row


@router.get("/companies/me/applications", response_model=list[ApplicationRead])
def applicants(job_id: int | None = None, status: Status | None = None,
               db=Depends(get_mongo), user: CurrentUser = Depends(require_company)):
    query: dict = {"company_id": user.id}
    if job_id is not None:
        job = db[JOBS].find_one({"_id": job_id}, {"company_id": 1})
        if job is None:
            raise HTTPException(404, "Job not found")
        if job["company_id"] != user.id:
            raise HTTPException(403, "You can only review your own jobs")
        query["job_id"] = job_id
    if status:
        query["status"] = status
    return repo.application_rows(db, query, NEWEST_FIRST)


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status


@router.patch("/applications/{application_id}/status", response_model=ApplicationRead)
def review(application_id: int, data: StatusUpdate, db=Depends(get_mongo),
           user: CurrentUser = Depends(require_company)):
    try:
        row, old_status = repo.update_application_status(
            db, application_id=application_id, company_id=user.id, status=data.status)
    except DomainError as err:
        raise HTTPException(err.status, err.message)
    for hook in on_status_changed:
        hook(row, old_status)
    return row
