"""p15-job routes on MongoDB: job postings and job search.

Each job document keeps a copy of its company's name (company_name) so
"search by title or company" is one indexed query instead of a join.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.schemas import JobBase, JobCreate, JobRead
from services.common import repo
from services.common.auth import CurrentUser, get_current_user, require_company
from services.common.mongo import COMPANIES, JOBS, get_mongo, log_activity, next_id, to_mongo, utcnow

router = APIRouter(tags=["Jobs"])

# Called after a job is created or edited; the Kafka producer (job.created)
# is attached here so routes stay unchanged.
on_job_saved = []


@router.post("/jobs", response_model=JobRead, status_code=201)
def create_job(job_data: JobCreate, db=Depends(get_mongo),
               user: CurrentUser = Depends(require_company)):
    if job_data.company_id != user.id:
        raise HTTPException(403, "Cannot create records for another user")
    company = db[COMPANIES].find_one({"_id": user.id}, {"company_name": 1})
    if company is None:
        raise HTTPException(409, "Create your company profile first")
    doc = to_mongo(job_data.model_dump())
    doc.update({"_id": next_id(db, JOBS), "company_name": company["company_name"],
                "created_at": utcnow()})
    db[JOBS].insert_one(doc)
    log_activity(db, user.id, "job_created", job_id=doc["_id"])
    job = repo.public_job(doc)
    for hook in on_job_saved:
        hook(job, created=True)
    return job


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(db=Depends(get_mongo), user: CurrentUser = Depends(get_current_user)):
    return [repo.public_job(d) for d in db[JOBS].find().sort("_id", -1)]


@router.get("/jobs/search", response_model=list[JobRead])
def search_jobs(q: str | None = None, location: str | None = None,
                category: str | None = None, is_remote: bool | None = None,
                db=Depends(get_mongo), user: CurrentUser = Depends(get_current_user)):
    query: dict = {}
    if q and q.strip():
        term = repo.ci_contains(q.strip())
        query["$or"] = [{"title": term}, {"company_name": term}]
    if location:
        query["location"] = repo.ci_contains(location)
    if category:
        query["category"] = category
    if is_remote is not None:
        query["is_remote"] = is_remote
    return [repo.public_job(d) for d in db[JOBS].find(query).sort("_id", -1)]


@router.get("/companies/me/jobs", response_model=list[JobRead])
def company_jobs(db=Depends(get_mongo), user: CurrentUser = Depends(require_company)):
    return [repo.public_job(d) for d in db[JOBS].find({"company_id": user.id}).sort("_id", -1)]


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, db=Depends(get_mongo), user: CurrentUser = Depends(get_current_user)):
    job = db[JOBS].find_one({"_id": job_id})
    if job is None:
        raise HTTPException(404, "Job not found")
    return repo.public_job(job)


@router.put("/jobs/{job_id}", response_model=JobRead)
def edit_job(job_id: int, data: JobBase, db=Depends(get_mongo),
             user: CurrentUser = Depends(require_company)):
    job = db[JOBS].find_one({"_id": job_id}, {"company_id": 1})
    if job is None:
        raise HTTPException(404, "Job not found")
    if job["company_id"] != user.id:
        raise HTTPException(403, "You can only edit your own jobs")
    db[JOBS].update_one({"_id": job_id}, {"$set": to_mongo(data.model_dump())})
    log_activity(db, user.id, "job_updated", job_id=job_id)
    updated = repo.public_job(db[JOBS].find_one({"_id": job_id}))
    for hook in on_job_saved:
        hook(updated, created=False)
    return updated
