from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, require_student, require_company
from app.database import get_db
from app.models.core import Company, Job, Student, User
from app.schemas import (
    CompanyBase,
    CompanyCreate,
    CompanyRead,
    JobCreate,
    JobRead,
    LoginRequest,
    LoginResponse,
    StudentBase,
    StudentCreate,
    StudentRead,
    UserCreate,
    UserRead,
)

router = APIRouter()

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


@router.post("/users/register", response_model=UserRead, status_code=201)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.scalar(
        select(User).where(User.email == user_data.email)
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail="Email is already registered",
        )

    user = User(
        email=user_data.email,
        password_hash=pwd_context.hash(user_data.password),
        role=user_data.role,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/users/login", response_model=LoginResponse)
def login_user(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(
        select(User).where(User.email == login_data.email)
    )

    if user is None or not pwd_context.verify(
        login_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account is inactive",
        )

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "message": "Login successful",
        "access_token": create_access_token(user),
        "token_type": "bearer",
    }


@router.get("/users/me", response_model=UserRead)
def current_user(user: User = Depends(get_current_user)):
    return user


@router.get("/students/me/dashboard", response_model=UserRead)
def student_dashboard(user: User = Depends(require_student)):
    return user


@router.get("/companies/me/dashboard", response_model=UserRead)
def company_dashboard(user: User = Depends(require_company)):
    return user


@router.post("/students", response_model=StudentRead, status_code=201)
def create_student(
    student_data: StudentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    if student_data.user_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot create records for another user")
    if db.get(Student, user.id) is not None:
        raise HTTPException(status_code=409, detail="Profile already exists")
    student = Student(**student_data.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("/students", response_model=list[StudentRead])
def list_students(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Student)).all()


@router.get("/students/{user_id}", response_model=StudentRead)
def get_student(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student = db.get(Student, user_id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    return student


@router.post("/companies", response_model=CompanyRead, status_code=201)
def create_company(
    company_data: CompanyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_company),
):
    if company_data.user_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot create records for another user")
    if db.get(Company, user.id) is not None:
        raise HTTPException(status_code=409, detail="Profile already exists")
    company = Company(**company_data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Company)).all()


@router.get("/companies/{user_id}", response_model=CompanyRead)
def get_company(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = db.get(Company, user_id)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    return company


@router.post("/jobs", response_model=JobRead, status_code=201)
def create_job(
    job_data: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_company),
):
    if job_data.company_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot create records for another user")
    if db.get(Company, user.id) is None:
        raise HTTPException(status_code=409, detail="Create your company profile first")
    job = Job(**job_data.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Job)).all()


@router.get("/jobs/search", response_model=list[JobRead])
def search_jobs(
    q: str | None = None,
    location: str | None = None,
    category: str | None = None,
    is_remote: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = select(Job)
    if q and q.strip():
        term = "%" + q.strip() + "%"
        statement = statement.join(Company).where(or_(Job.title.ilike(term), Company.company_name.ilike(term)))
    if location:
        statement = statement.where(Job.location.ilike(f"%{location}%"))
    if category:
        statement = statement.where(Job.category == category)
    if is_remote is not None:
        statement = statement.where(Job.is_remote == is_remote)
    return db.scalars(statement.order_by(Job.id.desc())).all()


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return job


@router.put("/students/{user_id}", response_model=StudentRead)
def update_student(
    user_id: int,
    profile_data: StudentBase,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    if user_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot modify another user's profile")
    profile = db.get(Student, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    for field, value in profile_data.model_dump().items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/companies/{user_id}", response_model=CompanyRead)
def update_company(
    user_id: int,
    profile_data: CompanyBase,
    db: Session = Depends(get_db),
    user: User = Depends(require_company),
):
    if user_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot modify another user's profile")
    profile = db.get(Company, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    for field, value in profile_data.model_dump().items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile
