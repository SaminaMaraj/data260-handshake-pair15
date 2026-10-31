"""p15-event routes on MongoDB: events, eligibility, and registrations.

Eligibility is stored as a structured object
    {"description": str, "majors": [str], "colleges": [str]}
instead of Lab 1's JSON string in a TEXT column.
"""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import EventRead as LegacyEventRead
from app.schemas import EventRegistrationCreate, EventRegistrationRead, StudentRead
from services.common import repo
from services.common.auth import CurrentUser, get_current_user, require_company, require_student
from services.common.mongo import (
    COMPANIES, EVENTS, REGISTRATIONS, STUDENTS, doc_out, get_mongo, log_activity,
    next_id, utcnow)
from services.common.repo import DomainError

router = APIRouter(tags=["Events"])

# Hook for the Kafka producer (event.registration_created).
on_registration_created = []


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    event_date: date
    event_time: time
    location: str = Field(min_length=1, max_length=255)
    eligibility: str = Field(default="", max_length=2000)
    eligible_majors: list[str] = Field(default_factory=list, max_length=50)
    eligible_colleges: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("event_time")
    @classmethod
    def local_time(cls, value):
        if value.tzinfo is not None:
            raise ValueError("Use local event time without a timezone offset")
        return value

    @field_validator("event_name", "description", "location")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()

    @field_validator("eligible_majors", "eligible_colleges")
    @classmethod
    def clean_rules(cls, values):
        if any(not v.strip() or len(v) > 255 for v in values):
            raise ValueError("Eligibility names must be 1–255 characters")
        return [v.strip() for v in values]

    def to_doc(self) -> dict:
        return {"event_name": self.event_name, "description": self.description,
                "event_date": self.event_date.isoformat(),
                "event_time": self.event_time.strftime("%H:%M:%S"),
                "location": self.location,
                "eligibility": {"description": self.eligibility,
                                "majors": self.eligible_majors,
                                "colleges": self.eligible_colleges}}


class EventRead(BaseModel):
    id: int
    company_id: int
    company_name: str
    event_name: str
    description: str
    event_date: date
    event_time: time
    location: str
    eligibility: str
    eligible_majors: list[str]
    eligible_colleges: list[str]
    eligible: bool
    ineligible_reason: str
    registered: bool


class RegistrationRead(BaseModel):
    student: StudentRead
    registered_at: datetime


class RegisterEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_eligibility: bool


def _future(data: EventInput) -> bool:
    return datetime.combine(data.event_date, data.event_time) > datetime.now()


def _legacy(event: dict) -> dict:
    """Lab 1's plain EventRead (legacy /events/search) for one stored event."""
    out = dict(event)
    out["eligibility"] = repo.event_rules(event)["description"]
    return out


# ---- static paths first (/events/search before /events/{event_id}) ---------------

@router.get("/events/search", response_model=list[LegacyEventRead])
def search_events(q: str | None = None, location: str | None = None,
                  from_date: date | None = None, db=Depends(get_mongo),
                  user: CurrentUser = Depends(get_current_user)):
    query: dict = {}
    if q:
        term = repo.ci_contains(q)
        query["$or"] = [{"event_name": term}, {"description": term},
                        {"eligibility.description": term}, {"eligibility.majors": term},
                        {"eligibility.colleges": term}]
    if location:
        query["location"] = repo.ci_contains(location)
    if from_date:
        query["event_date"] = {"$gte": from_date.isoformat()}
    return [_legacy(doc_out(d)) for d in db[EVENTS].find(query).sort("event_date", 1)]


@router.post("/event-registrations", response_model=EventRegistrationRead, status_code=201)
def register_for_event(registration_data: EventRegistrationCreate, db=Depends(get_mongo),
                       user: CurrentUser = Depends(require_student)):
    if registration_data.student_id != user.id:
        raise HTTPException(403, "You can only register yourself for an event")
    if db[EVENTS].find_one({"_id": registration_data.event_id}, {"_id": 1}) is None:
        raise HTTPException(404, "Event not found")
    if db[STUDENTS].find_one({"_id": registration_data.student_id}, {"_id": 1}) is None:
        raise HTTPException(404, "Student not found")
    if db[REGISTRATIONS].find_one({"event_id": registration_data.event_id,
                                   "student_id": registration_data.student_id}, {"_id": 1}):
        raise HTTPException(409, "Student is already registered for this event")
    try:
        registration, event = repo.create_registration(
            db, event_id=registration_data.event_id, student_id=user.id, user=user)
    except DomainError as err:
        message = err.message if err.status == 403 else "Event registration could not be saved"
        raise HTTPException(err.status, message)
    for hook in on_registration_created:
        hook(registration, event)
    return registration


@router.get("/event-registrations/student/{student_id}",
            response_model=list[EventRegistrationRead])
def list_student_event_registrations(student_id: int, db=Depends(get_mongo),
                                     user: CurrentUser = Depends(require_student)):
    if student_id != user.id:
        raise HTTPException(403, "You can only view your own registration history")
    if db[STUDENTS].find_one({"_id": student_id}, {"_id": 1}) is None:
        raise HTTPException(404, "Student not found")
    return [doc_out(r) for r in db[REGISTRATIONS].find({"student_id": student_id}).sort("_id", -1)]


@router.get("/event-registrations/{registration_id}", response_model=EventRegistrationRead)
def get_event_registration(registration_id: int, db=Depends(get_mongo),
                           user: CurrentUser = Depends(get_current_user)):
    registration = db[REGISTRATIONS].find_one({"_id": registration_id})
    if registration is None:
        raise HTTPException(404, "Event registration not found")
    event = db[EVENTS].find_one({"_id": registration["event_id"]}, {"company_id": 1})
    owns_registration = user.role == "student" and registration["student_id"] == user.id
    owns_event = user.role == "company" and event is not None and event["company_id"] == user.id
    if not (owns_registration or owns_event):
        raise HTTPException(403, "This registration is not available to your account")
    return doc_out(registration)


# ---- Part A event workflow ------------------------------------------------------

@router.get("/events", response_model=list[EventRead])
def events(q: str = "", mine: bool = False, registered: bool = False, upcoming: bool = True,
           db=Depends(get_mongo), user: CurrentUser = Depends(get_current_user)):
    query: dict = {}
    if mine:
        if user.role != "company":
            raise HTTPException(403, "Company account required")
        query["company_id"] = user.id
    if registered:
        if user.role != "student":
            raise HTTPException(403, "Student account required")
        ids = [r["event_id"] for r in db[REGISTRATIONS].find({"student_id": user.id}, {"event_id": 1})]
        query["_id"] = {"$in": ids}
    if q.strip():
        query["event_name"] = repo.ci_contains(q.strip())
    if upcoming:
        now = datetime.now()
        today, clock = now.date().isoformat(), now.strftime("%H:%M:%S")
        query["$or"] = [{"event_date": {"$gt": today}},
                        {"event_date": today, "event_time": {"$gt": clock}}]
    docs = db[EVENTS].find(query).sort([("event_date", 1), ("event_time", 1), ("_id", 1)])
    return [repo.event_output(db, doc_out(d), user) for d in docs]


@router.post("/events", status_code=201, response_model=EventRead)
def create_event(data: EventInput, db=Depends(get_mongo),
                 user: CurrentUser = Depends(require_company)):
    if db[COMPANIES].find_one({"_id": user.id}, {"_id": 1}) is None:
        raise HTTPException(409, "Create your company profile first")
    if not _future(data):
        raise HTTPException(422, "Event must be in the future")
    doc = {"_id": next_id(db, EVENTS), "company_id": user.id, **data.to_doc(),
           "created_at": utcnow()}
    db[EVENTS].insert_one(doc)
    log_activity(db, user.id, "event_created", event_id=doc["_id"])
    return repo.event_output(db, doc_out(doc), user)


@router.get("/events/{event_id}", response_model=EventRead)
def event_detail(event_id: int, db=Depends(get_mongo),
                 user: CurrentUser = Depends(get_current_user)):
    event = repo.get_event(db, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    return repo.event_output(db, event, user)


@router.put("/events/{event_id}", response_model=EventRead)
def update_event(event_id: int, data: EventInput, db=Depends(get_mongo),
                 user: CurrentUser = Depends(require_company)):
    event = db[EVENTS].find_one({"_id": event_id}, {"company_id": 1})
    if event is None:
        raise HTTPException(404, "Event not found")
    if event["company_id"] != user.id:
        raise HTTPException(403, "You can only edit your own events")
    if not _future(data):
        raise HTTPException(422, "Event must be in the future")
    db[EVENTS].update_one({"_id": event_id}, {"$set": data.to_doc()})
    return repo.event_output(db, repo.get_event(db, event_id), user)


@router.post("/events/{event_id}/registrations", status_code=201, response_model=EventRead)
def register_event(event_id: int, data: RegisterEvent, db=Depends(get_mongo),
                   user: CurrentUser = Depends(require_student)):
    event = repo.get_event(db, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    output = repo.event_output(db, event, user)
    if output["registered"]:
        raise HTTPException(409, "You are already registered for this event")
    if not output["eligible"]:
        raise HTTPException(403, output["ineligible_reason"])
    if not data.confirm_eligibility:
        raise HTTPException(422, "Confirm that you meet the stated eligibility requirements")
    try:
        registration, _ = repo.create_registration(db, event_id=event_id,
                                                   student_id=user.id, user=user)
    except DomainError as err:
        raise HTTPException(err.status, err.message)
    for hook in on_registration_created:
        hook(registration, event)
    return repo.event_output(db, event, user)


@router.get("/events/{event_id}/registrations", response_model=list[RegistrationRead])
def attendees(event_id: int, db=Depends(get_mongo),
              user: CurrentUser = Depends(require_company)):
    event = db[EVENTS].find_one({"_id": event_id}, {"company_id": 1})
    if event is None:
        raise HTTPException(404, "Event not found")
    if event["company_id"] != user.id:
        raise HTTPException(403, "You can only view registrations for your own events")
    regs = {r["student_id"]: r["registered_at"]
            for r in db[REGISTRATIONS].find({"event_id": event_id})}
    students = db[STUDENTS].find({"_id": {"$in": list(regs)}}).sort("full_name", 1)
    return [{"student": doc_out(s, "user_id"), "registered_at": regs[s["_id"]]} for s in students]
