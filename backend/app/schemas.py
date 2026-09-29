from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StudentBase(BaseModel):
    full_name: str
    college_name: str | None = None
    career_objective: str | None = None
    date_of_birth: date | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    degree: str | None = None
    major: str | None = None
    graduation_year: int | None = None
    cgpa: Decimal | None = None
    experience: str | None = None
    phone: str | None = None
    profile_picture_url: str | None = None
    skills_json: list | None = None


class StudentCreate(StudentBase):
    user_id: int


class StudentRead(StudentBase):
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class CompanyBase(BaseModel):
    company_name: str
    location: str | None = None
    description: str | None = None
    contact_phone: str | None = None
    profile_picture_url: str | None = None


class CompanyCreate(CompanyBase):
    user_id: int


class CompanyRead(CompanyBase):
    user_id: int

    model_config = ConfigDict(from_attributes=True)


JobCategory = Literal[
    "full_time",
    "part_time",
    "on_campus",
    "internship",
]


class JobBase(BaseModel):
    title: str
    posting_date: date
    deadline: date
    location: str
    salary: Decimal | None = None
    description: str
    category: JobCategory
    is_remote: bool = False
    skills_json: list | None = None


class JobCreate(JobBase):
    company_id: int


class JobRead(JobBase):
    id: int
    company_id: int

    model_config = ConfigDict(from_attributes=True)
from datetime import datetime
from pydantic import EmailStr


UserRole = Literal["student", "company"]


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: UserRole


class UserRead(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
