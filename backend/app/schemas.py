from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StudentBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    college_name: str | None = Field(default=None, max_length=255)
    career_objective: str | None = None
    date_of_birth: date | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    degree: str | None = Field(default=None, max_length=150)
    major: str | None = Field(default=None, max_length=150)
    graduation_year: int | None = Field(default=None, ge=1901, le=2155)
    cgpa: Decimal | None = Field(default=None, ge=0, max_digits=4, decimal_places=2)
    experience: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    profile_picture_url: str | None = Field(default=None, max_length=500)
    skills_json: list | None = None


    @field_validator("full_name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


class StudentCreate(StudentBase):
    user_id: int


class StudentRead(StudentBase):
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class CompanyBase(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = None
    contact_phone: str | None = Field(default=None, max_length=30)
    profile_picture_url: str | None = Field(default=None, max_length=500)


    @field_validator("company_name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


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
    title: str = Field(min_length=1, max_length=255)
    posting_date: date
    deadline: date
    location: str = Field(min_length=1, max_length=255)
    salary: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    description: str
    category: JobCategory
    is_remote: bool = False
    skills_json: list | None = None


    @field_validator("title", "location", "description")
    @classmethod
    def text_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def valid_dates(self):
        if self.deadline < self.posting_date:
            raise ValueError("Deadline must be on or after posting date")
        return self


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
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id: int
    email: EmailStr
    role: UserRole
    message: str


class ApplicationCreate(BaseModel):
    # Identity comes exclusively from the token; reject injected student/status fields.
    model_config = ConfigDict(extra="forbid")
    job_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)


class ApplicationRead(BaseModel):
    id: int
    job_id: int
    student_id: int
    resume_id: int
    status: Literal["pending", "reviewed", "declined"]
    applied_at: datetime
    reviewed_at: datetime | None
    job_title: str
    company_id: int
    company_name: str


class ResumeOption(BaseModel):
    id: int
    original_filename: str
    model_config = ConfigDict(from_attributes=True)
