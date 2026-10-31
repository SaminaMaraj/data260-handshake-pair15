"""p15-company routes on MongoDB: company profiles and the company dashboard."""
from fastapi import APIRouter, Depends, HTTPException

from app.schemas import CompanyBase, CompanyCreate, CompanyRead, UserRead
from services.common import repo
from services.common.auth import CurrentUser, get_current_user, require_company
from services.common.mongo import COMPANIES, JOBS, doc_out, get_mongo, log_activity, to_mongo

router = APIRouter(tags=["Companies"])


@router.get("/companies/me/dashboard", response_model=UserRead)
def company_dashboard(user: CurrentUser = Depends(require_company)):
    return user


@router.post("/companies", response_model=CompanyRead, status_code=201)
def create_company(company_data: CompanyCreate, db=Depends(get_mongo),
                   user: CurrentUser = Depends(require_company)):
    if company_data.user_id != user.id:
        raise HTTPException(403, "Cannot create records for another user")
    if db[COMPANIES].find_one({"_id": user.id}, {"_id": 1}):
        raise HTTPException(409, "Company profile already exists")
    data = company_data.model_dump()
    data["_id"] = data.pop("user_id")
    db[COMPANIES].insert_one(to_mongo(data))
    log_activity(db, user.id, "company_profile_created")
    return repo.get_company(db, user.id)


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(db=Depends(get_mongo), user: CurrentUser = Depends(get_current_user)):
    return [doc_out(d, "user_id") for d in db[COMPANIES].find().sort("company_name", 1)]


@router.get("/companies/{user_id}", response_model=CompanyRead)
def get_company(user_id: int, db=Depends(get_mongo),
                user: CurrentUser = Depends(get_current_user)):
    company = repo.get_company(db, user_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


@router.put("/companies/{user_id}", response_model=CompanyRead)
def update_company(user_id: int, profile_data: CompanyBase, db=Depends(get_mongo),
                   user: CurrentUser = Depends(require_company)):
    if user_id != user.id:
        raise HTTPException(403, "Cannot modify another user's profile")
    if db[COMPANIES].find_one({"_id": user.id}, {"_id": 1}) is None:
        raise HTTPException(404, "Profile not found")
    data = profile_data.model_dump()
    db[COMPANIES].update_one({"_id": user.id}, {"$set": to_mongo(data)})
    # Jobs carry a copy of the company name so job search needs no join;
    # keep that copy in step with the profile.
    db[JOBS].update_many({"company_id": user.id},
                         {"$set": {"company_name": data["company_name"]}})
    return repo.get_company(db, user.id)
