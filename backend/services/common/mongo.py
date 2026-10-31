"""MongoDB access shared by all p15 services (Lab 2 S3).

Database:  handshake_p15   (override with MONGO_DB)
Connection: MONGO_URL      e.g. mongodb://p15-mongo:27017
            "mongomock://" uses an in-process fake (tests only)

Storage conventions (one place, so every service writes the same shape):
  * Integer ids, kept from Lab 1 so the frontend and the assistant's
    JOB_IDS / rank_jobs contract do not change. New ids come from the
    `counters` collection (atomic $inc).  _id IS the id.
  * students/companies/preferences use the user id as _id.
  * Calendar dates are ISO strings "YYYY-MM-DD" and clock times "HH:MM:SS",
    so range queries and sorting work as plain string comparisons.
  * Money is Decimal128 (exact, like MySQL NUMERIC).
  * Timestamps are naive-UTC datetimes, as in Lab 1.
  * Files (resume PDFs, profile pictures) live in GridFS, so pods need no
    shared disk.
"""
import os
from datetime import date, datetime, time, timezone
from decimal import Decimal
from functools import lru_cache

from bson.decimal128 import Decimal128
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument

# ---- collection names (the contract shared with the Kafka workers) -------
USERS = "users"
STUDENTS = "students"
COMPANIES = "companies"
JOBS = "jobs"
APPLICATIONS = "applications"
RESUMES = "resumes"                    # metadata; bytes in GridFS bucket below
EVENTS = "events"
REGISTRATIONS = "event_registrations"
SAVED_ITEMS = "saved_items"
PREFERENCES = "student_preferences"
SESSIONS = "sessions"
ACTIVITY_LOGS = "activity_logs"
PENDING_ACTIONS = "pending_actions"    # assistant save confirmations
PROCESSED_EVENTS = "processed_events"  # Kafka consumer idempotency
ASSISTANT_RULES = "assistant_rules"
STUDENT_MEMORY = "student_memory"
CONVERSATIONS = "conversations"
COUNTERS = "counters"
RESUME_BUCKET = "resume_files"
PICTURE_BUCKET = "profile_pictures"

SESSION_TTL_MINUTES = 30        # matches the JWT lifetime
PENDING_TTL_SECONDS = 15 * 60   # assistant confirmation window


def client():
    """One pooled client per MONGO_URL (pymongo clients are thread-safe)."""
    return _client_for(os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017"))


@lru_cache(maxsize=4)
def _client_for(url: str):
    if url.startswith("mongomock://"):
        import mongomock
        return mongomock.MongoClient()
    from pymongo import MongoClient

    from services.common.tracing import MONGO_TIMER
    return MongoClient(url, serverSelectionTimeoutMS=3000, tz_aware=False,
                       event_listeners=[MONGO_TIMER])


def database():
    return client()[os.getenv("MONGO_DB", "handshake_p15")]


def get_mongo():
    """FastAPI dependency."""
    return database()


def next_id(db, name: str) -> int:
    doc = db[COUNTERS].find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return int(doc["seq"])


def set_counter_at_least(db, name: str, value: int) -> None:
    """After importing rows with known ids, make new ids continue after them."""
    db[COUNTERS].update_one({"_id": name}, {"$max": {"seq": int(value)}}, upsert=True)


def utcnow() -> datetime:
    """Naive UTC, truncated to milliseconds (BSON's precision) so a value
    reads back exactly as it was written."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


# ---- value conversion -----------------------------------------------------

def to_mongo(value):
    """Python values -> BSON-storable values (recursive)."""
    if isinstance(value, dict):
        return {k: to_mongo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_mongo(v) for v in value]
    if isinstance(value, Decimal):
        # Every decimal in the schema is NUMERIC(x, 2) in Lab 1 (salary,
        # minimum_salary, cgpa): store two places so 85000 reads back as
        # 85000.00, exactly as MySQL returned it.
        return Decimal128(value.quantize(Decimal("0.01")))
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return value


def from_mongo(value):
    """BSON values -> plain Python (Decimal128 -> Decimal)."""
    if isinstance(value, dict):
        return {k: from_mongo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_mongo(v) for v in value]
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return value


def doc_out(doc, id_field: str = "id"):
    """A stored document as an API dict: _id renamed to id/user_id/student_id."""
    if doc is None:
        return None
    out = from_mongo(dict(doc))
    out[id_field] = out.pop("_id")
    return out


# ---- indexes ----------------------------------------------------------------

def ensure_indexes(db) -> None:
    """Idempotent; every service calls this at startup."""
    db[USERS].create_index("email", unique=True)
    db[STUDENTS].create_indexes([IndexModel("full_name"), IndexModel("major"),
                                 IndexModel("college_name")])
    db[COMPANIES].create_index("company_name")
    db[JOBS].create_indexes([
        IndexModel([("company_id", ASCENDING), ("_id", DESCENDING)]),
        IndexModel("category"), IndexModel("location"), IndexModel("deadline"),
        IndexModel("company_name"), IndexModel("title"),
    ])
    db[APPLICATIONS].create_indexes([
        # One application per student per job: also makes Kafka replays harmless.
        IndexModel([("job_id", ASCENDING), ("student_id", ASCENDING)], unique=True),
        IndexModel([("student_id", ASCENDING), ("applied_at", DESCENDING)]),
        IndexModel([("company_id", ASCENDING), ("applied_at", DESCENDING)]),
    ])
    db[RESUMES].create_index("student_id")
    db[EVENTS].create_indexes([
        IndexModel([("event_date", ASCENDING), ("event_time", ASCENDING)]),
        IndexModel("company_id"),
    ])
    db[REGISTRATIONS].create_indexes([
        IndexModel([("event_id", ASCENDING), ("student_id", ASCENDING)], unique=True),
        IndexModel("student_id"),
    ])
    db[SAVED_ITEMS].create_indexes([
        IndexModel([("student_id", ASCENDING), ("job_id", ASCENDING)], unique=True,
                   partialFilterExpression={"job_id": {"$type": "number"}}),
        IndexModel([("student_id", ASCENDING), ("event_id", ASCENDING)], unique=True,
                   partialFilterExpression={"event_id": {"$type": "number"}}),
    ])
    # TTL indexes: MongoDB deletes the document once expires_at has passed.
    db[SESSIONS].create_index("expires_at", expireAfterSeconds=0)
    db[SESSIONS].create_index("user_id")
    db[PENDING_ACTIONS].create_index("expires_at", expireAfterSeconds=0)
    db[ACTIVITY_LOGS].create_index([("user_id", ASCENDING), ("at", DESCENDING)])
    db[ACTIVITY_LOGS].create_index("trace_id")
    db[PROCESSED_EVENTS].create_index("processed_at")
    db[STUDENT_MEMORY].create_index([("student_id", ASCENDING), ("date", ASCENDING)])
    db[CONVERSATIONS].create_index([("student_id", ASCENDING), ("updated_at", DESCENDING)])
    db["traces"].create_indexes([IndexModel("trace_id"), IndexModel([("at", DESCENDING)]),
                                 IndexModel([("service", ASCENDING), ("at", DESCENDING)])])
    db["token_usage"].create_index([("student_id", ASCENDING), ("at", DESCENDING)])


def log_activity(db, user_id, action: str, **details) -> None:
    """Append-only activity log; never lets logging break a request."""
    try:
        db[ACTIVITY_LOGS].insert_one({
            "user_id": user_id, "action": action, "at": utcnow(),
            "trace_id": details.pop("trace_id", None), "details": to_mongo(details)})
    except Exception:
        pass
