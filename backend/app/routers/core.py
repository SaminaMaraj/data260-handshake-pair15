from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.core import Company, Job, Student, User
from app.schemas import (
    CompanyCreate,
    CompanyRead,
    JobCreate,
    JobRead,
    LoginRequest,
    LoginResponse,
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
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
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
def login_user(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
):
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
    }


@router.post("/students", response_model=StudentRead, status_code=201)
def create_student(
    student_data: StudentCreate,
    db: Session = Depends(get_db),
):
    if db.get(User, student_data.user_id) is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if db.get(Student, student_data.user_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Student profile already exists",
        )

    student = Student(**student_data.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)

    return student


@router.get("/students", response_model=list[StudentRead])
def list_students(db: Session = Depends(get_db)):
    return db.scalars(select(Student).order_by(Student.user_id.asc())).all()


@router.get("/students/search", response_model=list[StudentRead])
def search_students(
    q: str | None = None,
    major: str | None = None,
    db: Session = Depends(get_db),
):
    statement = select(Student)

    if q:
        search_text = f"%{q}%"
        statement = statement.where(
            or_(
                Student.full_name.ilike(search_text),
                Student.college_name.ilike(search_text),
                Student.major.ilike(search_text),
                cast(Student.skills_json, String).ilike(search_text),
            )
        )

    if major:
        statement = statement.where(
            Student.major.ilike(f"%{major}%")
        )

    statement = statement.order_by(Student.full_name.asc())

    return db.scalars(statement).all()


@router.get("/students/{user_id}", response_model=StudentRead)
def get_student(
    user_id: int,
    db: Session = Depends(get_db),
):
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
):
    if db.get(User, company_data.user_id) is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if db.get(Company, company_data.user_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Company profile already exists",
        )

    company = Company(**company_data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)

    return company


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db)):
    return db.scalars(select(Company).order_by(Company.company_name.asc())).all()


@router.get("/companies/{user_id}", response_model=CompanyRead)
def get_company(
    user_id: int,
    db: Session = Depends(get_db),
):
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
):
    if db.get(Company, job_data.company_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    job = Job(**job_data.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)

    return job


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_db)):
    return db.scalars(select(Job).order_by(Job.id.desc())).all()


@router.get("/jobs/search", response_model=list[JobRead])
def search_jobs(
    q: str | None = None,
    location: str | None = None,
    category: str | None = None,
    is_remote: bool | None = None,
    db: Session = Depends(get_db),
):
    statement = (
        select(Job)
        .join(Company, Job.company_id == Company.user_id)
    )

    if q:
        search_text = f"%{q}%"
        statement = statement.where(
            or_(
                Job.title.ilike(search_text),
                Company.company_name.ilike(search_text),
            )
        )

    if location:
        statement = statement.where(
            Job.location.ilike(f"%{location}%")
        )

    if category:
        statement = statement.where(Job.category == category)

    if is_remote is not None:
        statement = statement.where(Job.is_remote == is_remote)

    statement = statement.order_by(Job.id.desc())

    return db.scalars(statement).all()


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return job