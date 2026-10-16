from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr


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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    message: str


class ApplicationCreate(BaseModel):
    job_id: int
    student_id: int
    resume_id: int

class ApplicationStatusUpdate(BaseModel):
    status: Literal["pending", "reviewed", "declined"]


class ApplicationRead(BaseModel):
    id: int
    job_id: int
    student_id: int
    resume_id: int
    status: str
    applied_at: datetime
    reviewed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

class EventCreate(BaseModel):
    company_id: int
    event_name: str
    description: str
    event_date: date
    event_time: time
    location: str
    eligibility: str | None = None


class EventRead(BaseModel):
    id: int
    company_id: int
    event_name: str
    description: str
    event_date: date
    event_time: time
    location: str
    eligibility: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventRegistrationCreate(BaseModel):
    event_id: int
    student_id: int


class EventRegistrationRead(BaseModel):
    id: int
    event_id: int
    student_id: int
    registered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResumeRead(BaseModel):
    id: int
    student_id: int
    original_filename: str
    stored_filename: str
    file_path: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)

class StudentPreferenceCreate(BaseModel):
    preferred_city: str | None = None
    preferred_category: JobCategory | None = None
    minimum_salary: Decimal | None = None
    preferred_skills_json: list | None = None
    remote_only: bool = False


class StudentPreferenceRead(StudentPreferenceCreate):
    student_id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SavedItemCreate(BaseModel):
    student_id: int
    job_id: int | None = None
    event_id: int | None = None


class SavedItemRead(BaseModel):
    id: int
    student_id: int
    job_id: int | None = None
    event_id: int | None = None
    saved_at: datetime

    model_config = ConfigDict(from_attributes=True)