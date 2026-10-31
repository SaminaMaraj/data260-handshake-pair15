"""Domain operations on MongoDB shared by routes, assistant tools and Kafka workers.

Anything that WRITES business data goes through a function here, so the
API path and the Kafka worker path produce identical documents. Kafka
workers (Bhavana) should call these, e.g.

    from services.common import repo
    from services.common.mongo import database
    repo.create_application(database(), job_id=..., student_id=..., resume_id=...)

Functions raise DomainError(status, message); routes turn it into an
HTTPException with the same status code and message Lab 1 used.
"""
import json
import re
from datetime import date, datetime

from pymongo.errors import DuplicateKeyError

from services.common.mongo import (
    APPLICATIONS, COMPANIES, EVENTS, JOBS, PREFERENCES, REGISTRATIONS, RESUMES,
    SAVED_ITEMS, STUDENTS, USERS, doc_out, from_mongo, log_activity, next_id,
    to_mongo, utcnow)


class DomainError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def ci_contains(text: str) -> dict:
    """Case-insensitive 'contains' (SQL ILIKE '%text%'), regex-escaped."""
    return {"$regex": re.escape(text), "$options": "i"}


def today_iso() -> str:
    return date.today().isoformat()


# ---- simple lookups -----------------------------------------------------------

def get_student(db, user_id):
    return doc_out(db[STUDENTS].find_one({"_id": user_id}), "user_id")


def get_company(db, user_id):
    return doc_out(db[COMPANIES].find_one({"_id": user_id}), "user_id")


def get_job(db, job_id):
    return doc_out(db[JOBS].find_one({"_id": job_id}))


def get_event(db, event_id):
    return doc_out(db[EVENTS].find_one({"_id": event_id}))


# ---- applications -------------------------------------------------------------

def application_rows(db, query: dict, sort) -> list[dict]:
    """Applications joined with job title, company and student name
    (Lab 1's application_query), using one lookup per referenced collection."""
    apps = list(db[APPLICATIONS].find(query).sort(sort))
    if not apps:
        return []
    jobs = {j["_id"]: j for j in db[JOBS].find(
        {"_id": {"$in": list({a["job_id"] for a in apps})}},
        {"title": 1, "company_id": 1})}
    company_ids = list({j["company_id"] for j in jobs.values()})
    companies = {c["_id"]: c["company_name"] for c in db[COMPANIES].find(
        {"_id": {"$in": company_ids}}, {"company_name": 1})}
    students = {s["_id"]: s["full_name"] for s in db[STUDENTS].find(
        {"_id": {"$in": list({a["student_id"] for a in apps})}}, {"full_name": 1})}
    rows = []
    for a in apps:
        job = jobs.get(a["job_id"])
        if job is None or a["student_id"] not in students or job["company_id"] not in companies:
            continue  # Lab 1 used inner joins: rows with a missing side drop out
        rows.append({
            "id": a["_id"], "job_id": a["job_id"], "student_id": a["student_id"],
            "resume_id": a["resume_id"], "status": a["status"],
            "applied_at": a["applied_at"], "reviewed_at": a.get("reviewed_at"),
            "job_title": job["title"], "company_id": job["company_id"],
            "company_name": companies[job["company_id"]],
            "student_name": students[a["student_id"]],
        })
    return rows


def application_row(db, application_id):
    rows = application_rows(db, {"_id": application_id}, [("_id", 1)])
    return rows[0] if rows else None


def create_application(db, *, job_id: int, student_id: int, resume_id: int,
                       trace_id: str | None = None, application_id: int | None = None):
    """Validate and insert one application (API and Kafka worker share this).

    Pass application_id to make a replayed message idempotent: inserting the
    same id twice, or the same (job, student) pair twice, is rejected by
    MongoDB's unique indexes instead of creating a duplicate.
    """
    job = db[JOBS].find_one({"_id": job_id})
    if job is None:
        raise DomainError(404, "Job not found")
    if job["deadline"] < today_iso():
        raise DomainError(409, "The application deadline has passed.")
    if db[STUDENTS].find_one({"_id": student_id}, {"_id": 1}) is None:
        raise DomainError(409, "Create your student profile before applying.")
    if db[APPLICATIONS].find_one({"job_id": job_id, "student_id": student_id}, {"_id": 1}):
        raise DomainError(409, "You have already applied to this job.")
    resume = db[RESUMES].find_one({"_id": resume_id})
    if resume is None:
        raise DomainError(404, "Resume not found")
    if resume["student_id"] != student_id:
        raise DomainError(403, "You can only use your own resume.")
    doc = {"_id": application_id or next_id(db, APPLICATIONS), "job_id": job_id,
           "student_id": student_id, "resume_id": resume_id,
           "company_id": job["company_id"], "status": "pending",
           "applied_at": utcnow(), "reviewed_at": None, "trace_id": trace_id}
    try:
        db[APPLICATIONS].insert_one(doc)
    except DuplicateKeyError:
        raise DomainError(409, "You have already applied to this job.")
    log_activity(db, student_id, "application_created", application_id=doc["_id"],
                 job_id=job_id, trace_id=trace_id)
    return application_row(db, doc["_id"])


def update_application_status(db, *, application_id: int, company_id: int,
                              status: str, trace_id: str | None = None):
    app = db[APPLICATIONS].find_one({"_id": application_id})
    if app is None:
        raise DomainError(404, "Application not found")
    job = db[JOBS].find_one({"_id": app["job_id"]}, {"company_id": 1})
    if job is None or job["company_id"] != company_id:
        raise DomainError(403, "You can only review your own applicants")
    reviewed_at = None if status == "pending" else utcnow()
    db[APPLICATIONS].update_one({"_id": application_id},
                                {"$set": {"status": status, "reviewed_at": reviewed_at}})
    log_activity(db, company_id, "application_status_changed",
                 application_id=application_id, old_status=app["status"],
                 new_status=status, trace_id=trace_id)
    return application_row(db, application_id), app["status"]


# ---- events -------------------------------------------------------------------

def event_rules(event: dict) -> dict:
    """Eligibility as {description, majors, colleges}.

    Lab 1 kept this as a JSON string in a TEXT column ("version": 1) or as
    plain text for older seed rows; Mongo stores the structured object."""
    raw = event.get("eligibility")
    if isinstance(raw, dict):
        return {"description": raw.get("description") or "",
                "majors": list(raw.get("majors") or []),
                "colleges": list(raw.get("colleges") or [])}
    try:
        data = json.loads(raw or "")
        if isinstance(data, dict) and data.get("version") == 1:
            return {"description": data.get("description") or "",
                    "majors": list(data.get("majors") or []),
                    "colleges": list(data.get("colleges") or [])}
    except (ValueError, TypeError):
        pass
    return {"description": raw or "", "majors": [], "colleges": []}


def eligibility(event: dict, student: dict | None):
    if student is None:
        return False, "Create your student profile first."
    rules = event_rules(event)
    for key, actual in (("majors", student.get("major")), ("colleges", student.get("college_name"))):
        if rules[key] and (actual or "").strip().casefold() not in [v.casefold() for v in rules[key]]:
            return False, "Your profile does not match the event " + key + " requirement."
    return True, ""


def event_is_upcoming(event: dict) -> bool:
    start = datetime.fromisoformat(f"{event['event_date']}T{event['event_time']}")
    return start > datetime.now()


def event_output(db, event: dict, user) -> dict:
    """The Part A EventRead shape for one event, as seen by ``user``."""
    rules = event_rules(event)
    if user.role == "student":
        ok, reason = eligibility(event, get_student(db, user.id))
    else:
        ok, reason = False, "Only students can register."
    if not event_is_upcoming(event):
        ok, reason = False, "Registration has closed."
    registered = db[REGISTRATIONS].find_one(
        {"event_id": event["id"], "student_id": user.id}, {"_id": 1}) is not None
    company = db[COMPANIES].find_one({"_id": event["company_id"]}, {"company_name": 1})
    return {"id": event["id"], "company_id": event["company_id"],
            "company_name": company["company_name"] if company else "",
            "event_name": event["event_name"], "description": event["description"],
            "event_date": event["event_date"], "event_time": event["event_time"],
            "location": event["location"], "eligibility": rules["description"],
            "eligible_majors": rules["majors"], "eligible_colleges": rules["colleges"],
            "eligible": ok, "ineligible_reason": reason, "registered": registered}


def create_registration(db, *, event_id: int, student_id: int, user,
                        trace_id: str | None = None, registration_id: int | None = None):
    """Eligibility-checked event registration (API and Kafka worker share this)."""
    event = get_event(db, event_id)
    if event is None:
        raise DomainError(404, "Event not found")
    output = event_output(db, event, user)
    if output["registered"]:
        raise DomainError(409, "You are already registered for this event")
    if not output["eligible"]:
        raise DomainError(403, output["ineligible_reason"])
    doc = {"_id": registration_id or next_id(db, REGISTRATIONS), "event_id": event_id,
           "student_id": student_id, "registered_at": utcnow(), "trace_id": trace_id}
    try:
        db[REGISTRATIONS].insert_one(doc)
    except DuplicateKeyError:
        raise DomainError(409, "You are already registered for this event")
    log_activity(db, student_id, "event_registered", event_id=event_id,
                 registration_id=doc["_id"], trace_id=trace_id)
    return doc_out(doc), event


# ---- saved items --------------------------------------------------------------

def save_item(db, *, student_id: int, job_id: int | None = None,
              event_id: int | None = None, if_exists: str = "error"):
    """Save one job or event. if_exists: "error" (409) or "return" the existing row."""
    if (job_id is None) == (event_id is None):
        raise DomainError(400, "Provide exactly one of job_id or event_id")
    if job_id is not None:
        if db[JOBS].find_one({"_id": job_id}, {"_id": 1}) is None:
            raise DomainError(404, "Job not found")
        key = {"student_id": student_id, "job_id": job_id}
    else:
        if db[EVENTS].find_one({"_id": event_id}, {"_id": 1}) is None:
            raise DomainError(404, "Event not found")
        key = {"student_id": student_id, "event_id": event_id}
    existing = db[SAVED_ITEMS].find_one(key)
    if existing is not None:
        if if_exists == "return":
            return doc_out(existing), False
        raise DomainError(409, "This item is already saved")
    doc = {"_id": next_id(db, SAVED_ITEMS), "student_id": student_id,
           "job_id": job_id, "event_id": event_id, "saved_at": utcnow()}
    try:
        db[SAVED_ITEMS].insert_one(doc)
    except DuplicateKeyError:
        if if_exists == "return":
            return doc_out(db[SAVED_ITEMS].find_one(key)), False
        raise DomainError(409, "This item is already saved")
    log_activity(db, student_id, "item_saved", job_id=job_id, event_id=event_id)
    return doc_out(doc), True


# ---- preferences ----------------------------------------------------------------

EVENT_PREFERENCE_FIELDS = {"preferred_event_majors_json", "preferred_event_city"}


def upsert_preferences(db, student_id: int, data: dict, fields_set: set) -> dict:
    """Save preferences; event fields the client did not send are kept."""
    update = {k: v for k, v in data.items()
              if not (k in EVENT_PREFERENCE_FIELDS and k not in fields_set)}
    update["updated_at"] = utcnow()
    db[PREFERENCES].update_one({"_id": student_id}, {"$set": to_mongo(update)}, upsert=True)
    return get_preferences(db, student_id)


def get_preferences(db, student_id: int):
    doc = db[PREFERENCES].find_one({"_id": student_id})
    if doc is None:
        return None
    out = doc_out(doc, "student_id")
    out.setdefault("remote_only", False)
    return out


def user_out(doc) -> dict:
    return {"id": doc["_id"], "email": doc["email"], "role": doc["role"],
            "is_active": doc.get("is_active", True), "created_at": doc["created_at"]}


def public_job(doc) -> dict:
    """A stored job as JobRead (drops the denormalized company_name)."""
    out = doc_out(doc)
    out.pop("company_name", None)
    out.pop("trace_id", None)
    return out
