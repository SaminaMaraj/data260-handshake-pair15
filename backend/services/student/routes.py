"""p15-student routes on MongoDB.

Owns identity for both roles (/users), student profiles and directory,
resumes and profile pictures (GridFS), preferences and saved items.
Request/response shapes, status codes and messages match Lab 1.
"""
import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import gridfs
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pymongo.errors import DuplicateKeyError
from pypdf import PdfReader

from app.schemas import (
    JobCategory, JobRead, LoginRequest, LoginResponse, ResumeOption, SavedItemCreate,
    SavedItemRead, StudentBase, StudentCreate, StudentPreferenceCreate,
    StudentPreferenceRead, StudentRead, UserCreate, UserRead)
from services.common import repo
from services.common.auth import (
    CurrentUser, end_session, get_current_user, hash_password, require_student,
    start_session, verify_password)
from services.common.mongo import (
    APPLICATIONS, COMPANIES, JOBS, PICTURE_BUCKET, RESUME_BUCKET, RESUMES,
    SAVED_ITEMS, STUDENTS, USERS, doc_out, get_mongo, log_activity, next_id,
    to_mongo, utcnow)
from services.common.repo import DomainError

router = APIRouter()


def _raise(err: DomainError):
    raise HTTPException(err.status, err.message)


# ---- identity (both roles) ------------------------------------------------------

@router.post("/users/register", response_model=UserRead, status_code=201, tags=["Users"])
def register_user(user_data: UserCreate, db=Depends(get_mongo)):
    if db[USERS].find_one({"email": user_data.email}, {"_id": 1}):
        raise HTTPException(409, "Email is already registered")
    now = utcnow()
    doc = {"_id": next_id(db, USERS), "email": user_data.email,
           "password_hash": hash_password(user_data.password), "role": user_data.role,
           "is_active": True, "created_at": now, "updated_at": now}
    try:
        db[USERS].insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Email is already registered")
    log_activity(db, doc["_id"], "register", role=doc["role"])
    return repo.user_out(doc)


@router.post("/users/login", response_model=LoginResponse, tags=["Users"])
def login_user(login_data: LoginRequest, request: Request, db=Depends(get_mongo)):
    user = db[USERS].find_one({"email": login_data.email})
    if user is None or not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(403, "User account is inactive")
    token = start_session(db, user, request.headers.get("user-agent"))
    return {"id": user["_id"], "email": user["email"], "role": user["role"],
            "message": "Login successful", "access_token": token, "token_type": "bearer"}


@router.post("/users/logout", status_code=204, tags=["Users"])
def logout_user(db=Depends(get_mongo), user: CurrentUser = Depends(get_current_user)):
    """Lab 2: revoke this token's server session (the JWT stops working)."""
    end_session(db, user)
    return Response(status_code=204)


@router.get("/users/me", response_model=UserRead, tags=["Users"])
def current_user(user: CurrentUser = Depends(get_current_user)):
    return user


class EmailUpdate(BaseModel):
    email: EmailStr


@router.put("/users/me", response_model=UserRead, tags=["Users"])
def update_email(data: EmailUpdate, db=Depends(get_mongo),
                 user: CurrentUser = Depends(get_current_user)):
    if db[USERS].find_one({"email": data.email, "_id": {"$ne": user.id}}, {"_id": 1}):
        raise HTTPException(409, "Email is already registered")
    try:
        db[USERS].update_one({"_id": user.id},
                             {"$set": {"email": data.email, "updated_at": utcnow()}})
    except DuplicateKeyError:
        raise HTTPException(409, "Email is already registered")
    return repo.user_out(db[USERS].find_one({"_id": user.id}))


@router.get("/students/me/dashboard", response_model=UserRead, tags=["Students"])
def student_dashboard(user: CurrentUser = Depends(require_student)):
    return user


# ---- student profiles -----------------------------------------------------------

@router.post("/students", response_model=StudentRead, status_code=201, tags=["Students"])
def create_student(student_data: StudentCreate, db=Depends(get_mongo),
                   user: CurrentUser = Depends(require_student)):
    if student_data.user_id != user.id:
        raise HTTPException(403, "Cannot create records for another user")
    if db[STUDENTS].find_one({"_id": user.id}, {"_id": 1}):
        raise HTTPException(409, "Student profile already exists")
    data = student_data.model_dump()
    data["_id"] = data.pop("user_id")
    db[STUDENTS].insert_one(to_mongo(data))
    return repo.get_student(db, user.id)


@router.get("/students", response_model=list[StudentRead], tags=["Students"])
def list_students(db=Depends(get_mongo), user: CurrentUser = Depends(get_current_user)):
    return [doc_out(d, "user_id") for d in db[STUDENTS].find().sort("_id", 1)]


@router.get("/students/search", response_model=list[StudentRead], tags=["Students"])
def search_students(q: str | None = None, major: str | None = None, db=Depends(get_mongo),
                    user: CurrentUser = Depends(get_current_user)):
    query: dict = {}
    if q:
        term = repo.ci_contains(q)
        query["$or"] = [{"full_name": term}, {"college_name": term},
                        {"major": term}, {"skills_json": term}]
    if major:
        query["major"] = repo.ci_contains(major)
    return [doc_out(d, "user_id") for d in db[STUDENTS].find(query).sort("full_name", 1)]


@router.get("/directory/students", response_model=list[StudentRead], tags=["Students"])
def directory(q: str = "", major: str = "", skill: str = "", db=Depends(get_mongo),
              user: CurrentUser = Depends(get_current_user)):
    query: dict = {}
    if q.strip():
        term = repo.ci_contains(q.strip())
        query["$or"] = [{"full_name": term}, {"college_name": term}, {"skills_json": term}]
    if major.strip():
        query["major"] = repo.ci_contains(major.strip())
    if skill.strip():
        query["skills_json"] = repo.ci_contains(skill.strip())
    docs = db[STUDENTS].find(query).sort([("full_name", 1), ("_id", 1)])
    return [doc_out(d, "user_id") for d in docs]


# ---- preferences and saved jobs (static /students/me/... before /{id}) ------------

class PreferenceInput(BaseModel):
    """Part A preferences shape (same validation as Lab 1's part_a.PreferenceInput)."""
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    preferred_city: str | None = Field(default=None, max_length=100)
    preferred_category: JobCategory | None = None
    minimum_salary: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    preferred_skills_json: list[str] | None = None
    remote_only: bool = False
    preferred_event_majors_json: list[str] | None = None
    preferred_event_city: str | None = Field(default=None, max_length=100)


def _part_a_preferences(stored: dict | None) -> PreferenceInput:
    """Only the Part A fields (the model forbids extra keys)."""
    if stored is None:
        return PreferenceInput()
    return PreferenceInput(**{k: stored.get(k) for k in PreferenceInput.model_fields
                              if stored.get(k) is not None})


@router.get("/students/me/preferences", response_model=PreferenceInput, tags=["Preferences"])
def my_preferences(db=Depends(get_mongo), user: CurrentUser = Depends(require_student)):
    return _part_a_preferences(repo.get_preferences(db, user.id))


@router.put("/students/me/preferences", response_model=PreferenceInput, tags=["Preferences"])
def update_my_preferences(data: PreferenceInput, db=Depends(get_mongo),
                          user: CurrentUser = Depends(require_student)):
    if repo.get_student(db, user.id) is None:
        raise HTTPException(409, "Create your student profile first")
    return _part_a_preferences(
        repo.upsert_preferences(db, user.id, data.model_dump(), data.model_fields_set))


@router.get("/students/me/saved-jobs", response_model=list[JobRead], tags=["Saved items"])
def saved_jobs(db=Depends(get_mongo), user: CurrentUser = Depends(require_student)):
    ids = [s["job_id"] for s in db[SAVED_ITEMS].find(
        {"student_id": user.id, "job_id": {"$type": "number"}}, {"job_id": 1})]
    return [repo.public_job(j) for j in db[JOBS].find({"_id": {"$in": ids}})]


@router.post("/students/me/saved-jobs/{job_id}", status_code=201, tags=["Saved items"])
def save_job(job_id: int, db=Depends(get_mongo), user: CurrentUser = Depends(require_student)):
    if repo.get_student(db, user.id) is None:
        raise HTTPException(409, "Create your student profile first")
    try:
        repo.save_item(db, student_id=user.id, job_id=job_id, if_exists="return")
    except DomainError as err:
        _raise(err)
    return {"saved": True, "job_id": job_id}


@router.get("/students/{user_id}", response_model=StudentRead, tags=["Students"])
def get_student(user_id: int, db=Depends(get_mongo),
                user: CurrentUser = Depends(get_current_user)):
    student = repo.get_student(db, user_id)
    if student is None:
        raise HTTPException(404, "Student not found")
    return student


@router.put("/students/{user_id}", response_model=StudentRead, tags=["Students"])
def update_student(user_id: int, profile_data: StudentBase, db=Depends(get_mongo),
                   user: CurrentUser = Depends(require_student)):
    if user_id != user.id:
        raise HTTPException(403, "Cannot modify another user's profile")
    if db[STUDENTS].find_one({"_id": user.id}, {"_id": 1}) is None:
        raise HTTPException(404, "Profile not found")
    db[STUDENTS].update_one({"_id": user.id}, {"$set": to_mongo(profile_data.model_dump())})
    return repo.get_student(db, user.id)


def _require_same_student(student_id: int, user: CurrentUser) -> None:
    if student_id != user.id:
        raise HTTPException(403, "You can only access your own data")


@router.put("/students/{student_id}/preferences", response_model=StudentPreferenceRead,
            tags=["Preferences"])
def save_student_preferences(student_id: int, preference_data: StudentPreferenceCreate,
                             db=Depends(get_mongo), user: CurrentUser = Depends(require_student)):
    _require_same_student(student_id, user)
    if repo.get_student(db, user.id) is None:
        raise HTTPException(404, "Student not found")
    return repo.upsert_preferences(db, user.id, preference_data.model_dump(),
                                   preference_data.model_fields_set)


@router.get("/students/{student_id}/preferences", response_model=StudentPreferenceRead,
            tags=["Preferences"])
def get_student_preferences(student_id: int, db=Depends(get_mongo),
                            user: CurrentUser = Depends(require_student)):
    _require_same_student(student_id, user)
    preference = repo.get_preferences(db, user.id)
    if preference is None:
        raise HTTPException(404, "No preferences saved for this student")
    return preference


# ---- saved items (legacy API) -------------------------------------------------------

@router.post("/saved-items", response_model=SavedItemRead, status_code=201, tags=["Saved items"])
def create_saved_item(saved_item_data: SavedItemCreate, db=Depends(get_mongo),
                      user: CurrentUser = Depends(require_student)):
    _require_same_student(saved_item_data.student_id, user)
    if (saved_item_data.job_id is None) == (saved_item_data.event_id is None):
        raise HTTPException(400, "Provide exactly one of job_id or event_id")
    if repo.get_student(db, user.id) is None:
        raise HTTPException(404, "Student not found")
    try:
        item, _ = repo.save_item(db, student_id=user.id, job_id=saved_item_data.job_id,
                                 event_id=saved_item_data.event_id)
    except DomainError as err:
        _raise(err)
    return item


@router.get("/saved-items/student/{student_id}", response_model=list[SavedItemRead],
            tags=["Saved items"])
def list_saved_items(student_id: int, db=Depends(get_mongo),
                     user: CurrentUser = Depends(require_student)):
    _require_same_student(student_id, user)
    if repo.get_student(db, user.id) is None:
        raise HTTPException(404, "Student not found")
    return [doc_out(d) for d in db[SAVED_ITEMS].find({"student_id": user.id}).sort("_id", -1)]


@router.delete("/saved-items/{saved_item_id}", status_code=204, tags=["Saved items"])
def delete_saved_item(saved_item_id: int, db=Depends(get_mongo),
                      user: CurrentUser = Depends(require_student)):
    item = db[SAVED_ITEMS].find_one({"_id": saved_item_id})
    if item is None:
        raise HTTPException(404, "Saved item not found")
    if item["student_id"] != user.id:
        raise HTTPException(403, "You can only delete your own saved items")
    db[SAVED_ITEMS].delete_one({"_id": saved_item_id})
    log_activity(db, user.id, "item_unsaved", saved_item_id=saved_item_id)
    return Response(status_code=204)


# ---- contact, resumes and pictures (files in GridFS) -----------------------------------

@router.get("/profiles/{user_id}/contact", tags=["Profiles"])
def contact(user_id: int, db=Depends(get_mongo), user: CurrentUser = Depends(get_current_user)):
    target = db[USERS].find_one({"_id": user_id}, {"email": 1})
    if target is None:
        raise HTTPException(404, "User not found")
    return {"email": target["email"]}


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    data = await file.read(limit + 1)
    await file.close()
    if not data or len(data) > limit:
        raise HTTPException(413, f"File must be nonempty and no larger than {limit // 1024 // 1024} MB")
    return data


@router.post("/resumes", response_model=ResumeOption, status_code=201, tags=["Resumes"])
async def upload_resume(file: UploadFile = File(...), db=Depends(get_mongo),
                        user: CurrentUser = Depends(require_student)):
    if repo.get_student(db, user.id) is None:
        raise HTTPException(409, "Create your student profile before uploading a resume.")
    data = await _read_upload(file, 5 * 1024 * 1024)
    if not (file.filename or "").lower().endswith(".pdf") or not data.startswith(b"%PDF-"):
        raise HTTPException(422, "Upload a valid PDF resume.")
    try:
        pdf = PdfReader(BytesIO(data))
        if pdf.is_encrypted or not len(pdf.pages):
            raise ValueError()
    except Exception:
        raise HTTPException(422, "PDF must be readable, unencrypted, and contain at least one page.")
    stored = uuid4().hex + ".pdf"
    bucket = gridfs.GridFSBucket(db, bucket_name=RESUME_BUCKET)
    file_id = bucket.upload_from_stream(stored, data, metadata={
        "student_id": user.id, "content_type": "application/pdf"})
    resume = {"_id": next_id(db, RESUMES), "student_id": user.id,
              "original_filename": Path(file.filename).name[:255],
              "stored_filename": stored, "file_path": f"gridfs://{RESUME_BUCKET}/{file_id}",
              "gridfs_id": file_id, "uploaded_at": utcnow()}
    try:
        db[RESUMES].insert_one(resume)
    except Exception:
        bucket.delete(file_id)
        raise HTTPException(503, "Resume could not be saved. Please retry.")
    log_activity(db, user.id, "resume_uploaded", resume_id=resume["_id"])
    return {"id": resume["_id"], "original_filename": resume["original_filename"]}


@router.get("/resumes/{resume_id}/file", responses={200: {"content": {"application/pdf": {}}}},
            tags=["Resumes"])
def resume_file(resume_id: int, db=Depends(get_mongo),
                user: CurrentUser = Depends(get_current_user)):
    resume = db[RESUMES].find_one({"_id": resume_id})
    if resume is None:
        raise HTTPException(404, "Resume not found")
    permitted = user.role == "student" and resume["student_id"] == user.id
    if user.role == "company":
        permitted = db[APPLICATIONS].find_one(
            {"resume_id": resume_id, "company_id": user.id}, {"_id": 1}) is not None
    if not permitted:
        raise HTTPException(403, "This resume is not available to your account")
    if not resume.get("gridfs_id"):
        raise HTTPException(404, "No uploaded PDF is available for this fixture resume")
    try:
        data = gridfs.GridFSBucket(db, bucket_name=RESUME_BUCKET).open_download_stream(
            resume["gridfs_id"]).read()
    except gridfs.errors.NoFile:
        raise HTTPException(404, "No uploaded PDF is available for this fixture resume")
    name = resume["original_filename"].replace('"', "")
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{name}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.post("/profiles/me/picture", tags=["Profiles"])
async def upload_picture(file: UploadFile = File(...), db=Depends(get_mongo),
                         user: CurrentUser = Depends(get_current_user)):
    collection = STUDENTS if user.role == "student" else COMPANIES
    if db[collection].find_one({"_id": user.id}, {"_id": 1}) is None:
        raise HTTPException(409, "Create your profile before uploading a picture")
    data = await _read_upload(file, 3 * 1024 * 1024)
    try:
        image = Image.open(BytesIO(data))
        if image.format not in ("PNG", "JPEG") or image.width * image.height > 16_000_000:
            raise ValueError()
        image.verify()
        image = Image.open(BytesIO(data)).convert("RGB")
        image.thumbnail((800, 800))
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(422, "Upload a valid PNG or JPEG image (at most 16 megapixels)")
    out = BytesIO()
    image.save(out, format="JPEG")
    name = uuid4().hex + ".jpg"
    gridfs.GridFSBucket(db, bucket_name=PICTURE_BUCKET).upload_from_stream(
        name, out.getvalue(), metadata={"user_id": user.id, "content_type": "image/jpeg"})
    url = "/media/profile/" + name
    db[collection].update_one({"_id": user.id}, {"$set": {"profile_picture_url": url}})
    return {"profile_picture_url": url}


@router.get("/media/profile/{filename}", tags=["Profiles"])
def picture(filename: str, db=Depends(get_mongo),
            user: CurrentUser = Depends(get_current_user)):
    if not re.fullmatch(r"[a-f0-9]{32}\.jpg", filename):
        raise HTTPException(404, "Picture not found")
    try:
        data = gridfs.GridFSBucket(db, bucket_name=PICTURE_BUCKET).open_download_stream_by_name(
            filename).read()
    except gridfs.errors.NoFile:
        raise HTTPException(404, "Picture not found")
    return Response(data, media_type="image/jpeg")
