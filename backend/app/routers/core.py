from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy import select
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
