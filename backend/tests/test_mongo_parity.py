"""Lab 2 S5: the MongoDB services behave exactly like the Lab 1 SQL monolith.

One scripted scenario (about 80 API calls: sign-up, login, profiles, jobs,
search, resume upload, applications, company review, events, eligibility,
registrations, preferences, saved items, authorization failures and
validation errors) runs twice:

  A. the Lab 1 monolith (app/main.py) on an in-memory SQL database
  B. the six Lab 2 services on MongoDB, each request sent to the service
     that owns its path (what the gateway does)

Every step must return the same status code and the same JSON body. Only
values that are random by nature are normalized: timestamps, JWTs and
uploaded-file names. Ids are compared as-is, so the Mongo counters must
hand out the same ids as SQL autoincrement.

Needs MongoDB (MONGO_URL, default mongodb://127.0.0.1:27017); skipped if
it is not reachable. Run from backend/:
    python -m pytest tests/test_mongo_parity.py -q
"""
import os
import re
import sys
import uuid
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "parity-test-key-not-for-production-use-0123")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(BigInteger, "sqlite")
def _sqlite_bigint(element, compiler, **kwargs):
    return "INTEGER"


TIMESTAMP_KEYS = {"created_at", "updated_at", "applied_at", "reviewed_at",
                  "registered_at", "saved_at", "uploaded_at"}
FUTURE = (date.today() + timedelta(days=30)).isoformat()
SOON = (date.today() + timedelta(days=10)).isoformat()
PAST = (date.today() - timedelta(days=5)).isoformat()


def tiny_pdf() -> bytes:
    from pypdf import PdfWriter
    writer, out = PdfWriter(), BytesIO()
    writer.add_blank_page(width=200, height=200)
    writer.write(out)
    return out.getvalue()


def tiny_png() -> bytes:
    out = BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


def normalize(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in TIMESTAMP_KEYS:
                out[k] = None if v is None else "<timestamp>"
            elif k == "access_token":
                out[k] = "<jwt>"
            elif k == "profile_picture_url" and isinstance(v, str):
                out[k] = re.sub(r"[a-f0-9]{32}", "<file>", v)
            else:
                out[k] = normalize(v)
        return out
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


# ---- the two backends -------------------------------------------------------------

class Backend:
    """Sends requests, remembers tokens by account name."""

    def __init__(self, client_for):
        self.client_for = client_for
        self.tokens = {}

    def call(self, method, path, who=None, **kwargs):
        headers = kwargs.pop("headers", {})
        if who:
            headers["Authorization"] = f"Bearer {self.tokens[who]}"
        res = self.client_for(path).request(method, path, headers=headers, **kwargs)
        if res.status_code == 204:
            # No body by definition. (Lab 1 also sent a JSON content-type
            # header on its empty 204s; Lab 2 does not.)
            return 204, None
        try:
            body = res.json()
        except ValueError:
            body = {"_content_type": res.headers.get("content-type"),
                    "_bytes": len(res.content)}
        return res.status_code, body


@pytest.fixture(scope="module")
def backends(tmp_path_factory):
    # A: Lab 1 monolith on in-memory SQLite (same approach as the Lab 1 tests).
    from app.database import Base, get_db
    from app.main import app as monolith
    import app.routers.part_a as part_a
    part_a.UPLOADS = tmp_path_factory.mktemp("uploads")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    monolith.dependency_overrides[get_db] = override
    sql_client = TestClient(monolith, raise_server_exceptions=False)

    # B: six Mongo services in a throwaway database.
    from services.common import mongo
    try:
        mongo.client().admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    db_name = f"p15_parity_{uuid.uuid4().hex[:8]}"
    os.environ["MONGO_DB"] = db_name
    from services.common.app_factory import build_service_app
    from services.common.routing import SERVICE_PORTS, owner_of
    clients = {}
    for name in SERVICE_PORTS:
        client = TestClient(build_service_app(name), raise_server_exceptions=False)
        client.__enter__()  # run startup (indexes)
        clients[name] = client

    yield Backend(lambda path: sql_client), Backend(lambda path: clients[owner_of(path)])

    for client in clients.values():
        client.__exit__(None, None, None)
    monolith.dependency_overrides.clear()
    mongo.client().drop_database(db_name)


# ---- the scenario ---------------------------------------------------------------------
# (label, method, path, who, kwargs, options)
# options: "unordered" -> compare list bodies ignoring order;
#          "token:<name>" -> remember access_token under <name>.

PDF = tiny_pdf()
PNG = tiny_png()


def job(company_id, title, category="internship", location="Sunnyvale", salary=85000,
        remote=False, skills=("Python", "SQL"), deadline=FUTURE):
    return {"company_id": company_id, "title": title, "posting_date": date.today().isoformat(),
            "deadline": deadline, "location": location, "salary": salary,
            "description": f"{title} role", "category": category, "is_remote": remote,
            "skills_json": list(skills)}


def event(name, majors=(), when=FUTURE):
    return {"event_name": name, "description": f"{name} for students", "event_date": when,
            "event_time": "14:00:00", "location": "Palo Alto",
            "eligibility": "Open to listed majors", "eligible_majors": list(majors),
            "eligible_colleges": []}


STUDENT_A = {"user_id": 1, "full_name": "Ana Rivera", "college_name": "San Jose State University",
             "major": "Computer Science", "city": "Sunnyvale", "cgpa": 3.7,
             "skills_json": ["Python", "SQL", "React"], "graduation_year": 2027}
STUDENT_B = {"user_id": 2, "full_name": "Ben Ortiz", "college_name": "Foothill College",
             "major": "History", "city": "Cupertino", "skills_json": ["Writing"]}

SCENARIO = [
    # accounts
    ("register student A", "POST", "/users/register", None,
     {"json": {"email": "ana@p15.dev", "password": "StrongPass1!", "role": "student"}}, ""),
    ("register student B", "POST", "/users/register", None,
     {"json": {"email": "ben@p15.dev", "password": "StrongPass1!", "role": "student"}}, ""),
    ("register company C", "POST", "/users/register", None,
     {"json": {"email": "hr@cascade.dev", "password": "StrongPass1!", "role": "company"}}, ""),
    ("register company D", "POST", "/users/register", None,
     {"json": {"email": "hr@delta.dev", "password": "StrongPass1!", "role": "company"}}, ""),
    ("duplicate email", "POST", "/users/register", None,
     {"json": {"email": "ana@p15.dev", "password": "StrongPass1!", "role": "student"}}, ""),
    ("short password", "POST", "/users/register", None,
     {"json": {"email": "x@p15.dev", "password": "short", "role": "student"}}, ""),
    ("login A", "POST", "/users/login", None,
     {"json": {"email": "ana@p15.dev", "password": "StrongPass1!"}}, "token:A"),
    ("login B", "POST", "/users/login", None,
     {"json": {"email": "ben@p15.dev", "password": "StrongPass1!"}}, "token:B"),
    ("login C", "POST", "/users/login", None,
     {"json": {"email": "hr@cascade.dev", "password": "StrongPass1!"}}, "token:C"),
    ("login D", "POST", "/users/login", None,
     {"json": {"email": "hr@delta.dev", "password": "StrongPass1!"}}, "token:D"),
    ("wrong password", "POST", "/users/login", None,
     {"json": {"email": "ana@p15.dev", "password": "WrongPass1!"}}, ""),
    ("me without token", "GET", "/users/me", None, {}, ""),
    ("me", "GET", "/users/me", "A", {}, ""),
    ("student dashboard as company", "GET", "/students/me/dashboard", "C", {}, ""),
    ("company dashboard", "GET", "/companies/me/dashboard", "C", {}, ""),
    # profiles
    ("profile for another user", "POST", "/students", "A",
     {"json": {**STUDENT_A, "user_id": 2}}, ""),
    ("profile A", "POST", "/students", "A", {"json": STUDENT_A}, ""),
    ("profile B", "POST", "/students", "B", {"json": STUDENT_B}, ""),
    ("profile A again", "POST", "/students", "A", {"json": STUDENT_A}, ""),
    ("company C", "POST", "/companies", "C",
     {"json": {"user_id": 3, "company_name": "Cascade Analytics", "location": "Sunnyvale",
               "description": "Data tools"}}, ""),
    ("company D", "POST", "/companies", "D",
     {"json": {"user_id": 4, "company_name": "Delta Robotics", "location": "Cupertino"}}, ""),
    ("company as student", "POST", "/companies", "A",
     {"json": {"user_id": 1, "company_name": "Nope"}}, ""),
    # jobs
    ("job 1", "POST", "/jobs", "C", {"json": job(3, "Data Analyst Intern", remote=True)}, ""),
    ("job 2", "POST", "/jobs", "C",
     {"json": job(3, "Backend Engineer", "full_time", "Palo Alto", 140000, skills=("Python", "FastAPI"))}, ""),
    ("job 3 past deadline", "POST", "/jobs", "C",
     {"json": {**job(3, "Archived Role", deadline=PAST),
               "posting_date": (date.today() - timedelta(days=20)).isoformat()}}, ""),
    ("job 4", "POST", "/jobs", "D", {"json": job(4, "Robotics Intern", location="Cupertino", salary=None)}, ""),
    ("job for other company", "POST", "/jobs", "D", {"json": job(3, "Spoof")}, ""),
    ("job bad dates", "POST", "/jobs", "C",
     {"json": {**job(3, "Bad"), "deadline": PAST}}, ""),
    ("list jobs", "GET", "/jobs", "A", {}, ""),
    ("search title", "GET", "/jobs/search", "A", {"params": {"q": "intern"}}, ""),
    ("search company name", "GET", "/jobs/search", "A", {"params": {"q": "cascade"}}, ""),
    ("search city+category", "GET", "/jobs/search", "A",
     {"params": {"location": "sunny", "category": "internship"}}, ""),
    ("search remote", "GET", "/jobs/search", "A", {"params": {"is_remote": "true"}}, ""),
    ("search no match", "GET", "/jobs/search", "A", {"params": {"q": "nonexistent labs"}}, ""),
    ("job detail", "GET", "/jobs/2", "A", {}, ""),
    ("job 404", "GET", "/jobs/999", "A", {}, ""),
    ("company jobs", "GET", "/companies/me/jobs", "C", {}, ""),
    ("edit other company's job", "PUT", "/jobs/1", "D", {"json": job(3, "Hijack")}, ""),
    ("edit own job", "PUT", "/jobs/1", "C",
     {"json": {k: v for k, v in job(3, "Data Analyst Intern (Summer)", remote=True).items()
               if k != "company_id"}}, ""),
    ("list companies", "GET", "/companies", "A", {}, ""),
    ("company detail", "GET", "/companies/4", "A", {}, ""),
    ("company 404", "GET", "/companies/99", "A", {}, ""),
    # students and directory
    ("list students", "GET", "/students", "C", {}, ""),
    ("student search skill", "GET", "/students/search", "C", {"params": {"q": "python"}}, ""),
    ("student search major", "GET", "/students/search", "C", {"params": {"major": "hist"}}, ""),
    ("directory q", "GET", "/directory/students", "C", {"params": {"q": "san jose"}}, ""),
    ("directory skill", "GET", "/directory/students", "C", {"params": {"skill": "react"}}, ""),
    ("student detail", "GET", "/students/2", "C", {}, ""),
    ("student 404", "GET", "/students/99", "C", {}, ""),
    ("contact", "GET", "/profiles/3/contact", "A", {}, ""),
    # resumes and applications
    ("resume not pdf", "POST", "/resumes", "A",
     {"files": {"file": ("cv.txt", b"hello", "text/plain")}}, ""),
    ("resume A", "POST", "/resumes", "A", {"files": {"file": ("ana_cv.pdf", PDF, "application/pdf")}}, ""),
    ("resume B", "POST", "/resumes", "B", {"files": {"file": ("ben_cv.pdf", PDF, "application/pdf")}}, ""),
    ("resume options", "GET", "/applications/resume-options", "A", {}, ""),
    ("apply job 1", "POST", "/applications", "A", {"json": {"job_id": 1, "resume_id": 1}}, ""),
    ("apply job 2", "POST", "/applications", "A", {"json": {"job_id": 2, "resume_id": 1}}, ""),
    ("apply again", "POST", "/applications", "A", {"json": {"job_id": 1, "resume_id": 1}}, ""),
    ("apply past deadline", "POST", "/applications", "A", {"json": {"job_id": 3, "resume_id": 1}}, ""),
    ("apply with B's resume", "POST", "/applications", "A", {"json": {"job_id": 4, "resume_id": 2}}, ""),
    ("apply missing job", "POST", "/applications", "A", {"json": {"job_id": 999, "resume_id": 1}}, ""),
    ("apply extra field", "POST", "/applications", "A",
     {"json": {"job_id": 4, "resume_id": 1, "student_id": 2}}, ""),
    ("B applies job 1", "POST", "/applications", "B", {"json": {"job_id": 1, "resume_id": 2}}, ""),
    ("my applications", "GET", "/applications", "A", {}, ""),
    ("my applications pending", "GET", "/applications", "A", {"params": {"status": "pending"}}, ""),
    ("application detail", "GET", "/applications/1", "A", {}, ""),
    ("other's application", "GET", "/applications/3", "A", {}, ""),
    ("applications by student id", "GET", "/applications/student/1", "A", {}, ""),
    ("applications of other student", "GET", "/applications/student/2", "A", {}, ""),
    ("company applicants", "GET", "/companies/me/applications", "C", {}, ""),
    ("applicants for job 1", "GET", "/companies/me/applications", "C", {"params": {"job_id": 1}}, ""),
    ("applicants other's job", "GET", "/companies/me/applications", "C", {"params": {"job_id": 4}}, ""),
    ("review", "PATCH", "/applications/1/status", "C", {"json": {"status": "reviewed"}}, ""),
    ("decline", "PATCH", "/applications/3/status", "C", {"json": {"status": "declined"}}, ""),
    ("review other's applicant", "PATCH", "/applications/2/status", "D",
     {"json": {"status": "declined"}}, ""),
    ("bad status", "PATCH", "/applications/1/status", "C", {"json": {"status": "hired"}}, ""),
    ("applicants reviewed", "GET", "/companies/me/applications", "C", {"params": {"status": "reviewed"}}, ""),
    ("resume file own", "GET", "/resumes/1/file", "A", {}, ""),
    ("resume file applicant's company", "GET", "/resumes/1/file", "C", {}, ""),
    ("resume file other company", "GET", "/resumes/1/file", "D", {}, ""),
    ("resume file other student", "GET", "/resumes/1/file", "B", {}, ""),
    # events
    ("event CS only", "POST", "/events", "C", {"json": event("CS Career Night", ["Computer Science"])}, ""),
    ("event open", "POST", "/events", "D", {"json": event("Robotics Open House", when=SOON)}, ""),
    ("event in past", "POST", "/events", "C", {"json": event("Old", when=PAST)}, ""),
    ("event as student", "POST", "/events", "A", {"json": event("Nope")}, ""),
    ("events for A", "GET", "/events", "A", {}, ""),
    ("events for B", "GET", "/events", "B", {}, ""),
    ("event detail", "GET", "/events/1", "A", {}, ""),
    ("event 404", "GET", "/events/99", "A", {}, ""),
    ("register unconfirmed", "POST", "/events/1/registrations", "A",
     {"json": {"confirm_eligibility": False}}, ""),
    ("register eligible", "POST", "/events/1/registrations", "A",
     {"json": {"confirm_eligibility": True}}, ""),
    ("register again", "POST", "/events/1/registrations", "A",
     {"json": {"confirm_eligibility": True}}, ""),
    ("register ineligible major", "POST", "/events/1/registrations", "B",
     {"json": {"confirm_eligibility": True}}, ""),
    ("legacy register", "POST", "/event-registrations", "B",
     {"json": {"event_id": 2, "student_id": 2}}, ""),
    ("legacy register for other", "POST", "/event-registrations", "B",
     {"json": {"event_id": 2, "student_id": 1}}, ""),
    ("legacy history", "GET", "/event-registrations/student/2", "B", {}, ""),
    ("legacy registration detail owner company", "GET", "/event-registrations/2", "D", {}, ""),
    ("legacy registration detail stranger", "GET", "/event-registrations/2", "C", {}, ""),
    ("registered events", "GET", "/events", "A", {"params": {"registered": "true"}}, ""),
    ("my events", "GET", "/events", "C", {"params": {"mine": "true"}}, ""),
    ("search events by name", "GET", "/events", "A", {"params": {"q": "robot"}}, ""),
    ("attendees", "GET", "/events/1/registrations", "C", {}, ""),
    ("attendees not owner", "GET", "/events/1/registrations", "D", {}, ""),
    ("legacy event search", "GET", "/events/search", "A", {"params": {"location": "palo"}}, "legacy_events"),
    ("edit other's event", "PUT", "/events/1", "D", {"json": event("Hijack")}, ""),
    ("edit own event", "PUT", "/events/1", "C",
     {"json": event("CS Career Night (updated)", ["Computer Science", "Data Science"])}, ""),
    # preferences
    ("prefs empty", "GET", "/students/me/preferences", "A", {}, ""),
    ("prefs save", "PUT", "/students/me/preferences", "A",
     {"json": {"preferred_city": "Sunnyvale", "preferred_category": "internship",
               "minimum_salary": 70000, "preferred_skills_json": ["Python", "SQL"],
               "remote_only": False, "preferred_event_majors_json": ["Computer Science"],
               "preferred_event_city": "Sunnyvale"}}, ""),
    ("prefs update keeps event prefs", "PUT", "/students/me/preferences", "A",
     {"json": {"preferred_city": "Palo Alto", "remote_only": True}}, ""),
    ("prefs read", "GET", "/students/me/preferences", "A", {}, ""),
    ("prefs by id", "GET", "/students/1/preferences", "A", {}, ""),
    ("prefs of other", "GET", "/students/2/preferences", "A", {}, ""),
    ("prefs none saved", "GET", "/students/2/preferences", "B", {}, ""),
    ("prefs legacy put", "PUT", "/students/2/preferences", "B",
     {"json": {"preferred_city": "Cupertino", "minimum_salary": 50000.5}}, ""),
    ("prefs bad category", "PUT", "/students/me/preferences", "A",
     {"json": {"preferred_category": "gig"}}, ""),
    # saved items
    ("save job", "POST", "/students/me/saved-jobs/2", "A", {}, ""),
    ("save job again", "POST", "/students/me/saved-jobs/2", "A", {}, ""),
    ("save missing job", "POST", "/students/me/saved-jobs/999", "A", {}, ""),
    ("save event", "POST", "/saved-items", "A", {"json": {"student_id": 1, "event_id": 2}}, ""),
    ("save event again", "POST", "/saved-items", "A", {"json": {"student_id": 1, "event_id": 2}}, ""),
    ("save both", "POST", "/saved-items", "A", {"json": {"student_id": 1, "job_id": 1, "event_id": 2}}, ""),
    ("save for other", "POST", "/saved-items", "A", {"json": {"student_id": 2, "job_id": 1}}, ""),
    ("saved jobs", "GET", "/students/me/saved-jobs", "A", {}, "unordered"),
    ("saved items", "GET", "/saved-items/student/1", "A", {}, ""),
    ("delete other's saved item", "DELETE", "/saved-items/1", "B", {}, ""),
    ("delete saved item", "DELETE", "/saved-items/2", "A", {}, ""),
    ("delete missing", "DELETE", "/saved-items/2", "A", {}, ""),
    # profile updates
    ("update other's profile", "PUT", "/students/2", "A", {"json": STUDENT_A}, ""),
    ("update profile", "PUT", "/students/1", "A",
     {"json": {k: v for k, v in STUDENT_A.items() if k != "user_id"} | {"city": "Palo Alto"}}, ""),
    ("rename company", "PUT", "/companies/3", "C",
     {"json": {"company_name": "Cascade Data Labs", "location": "Sunnyvale"}}, ""),
    ("search by new company name", "GET", "/jobs/search", "A", {"params": {"q": "data labs"}}, ""),
    ("applications show new name", "GET", "/applications", "A", {}, ""),
    ("change email", "PUT", "/users/me", "A", {"json": {"email": "ana.r@p15.dev"}}, ""),
    ("change to taken email", "PUT", "/users/me", "A", {"json": {"email": "ben@p15.dev"}}, ""),
    ("login with new email", "POST", "/users/login", None,
     {"json": {"email": "ana.r@p15.dev", "password": "StrongPass1!"}}, ""),
    ("picture", "POST", "/profiles/me/picture", "C",
     {"files": {"file": ("logo.png", PNG, "image/png")}}, ""),
    ("picture bad", "POST", "/profiles/me/picture", "C",
     {"files": {"file": ("logo.png", b"not an image", "image/png")}}, ""),
]


def test_scenario_is_large(backends):
    assert len(SCENARIO) >= 120


def test_mongo_services_match_lab1_monolith(backends):
    sql, mongo = backends
    mismatches = []
    statuses = {}
    for label, method, path, who, kwargs, options in SCENARIO:
        a = sql.call(method, path, who, **kwargs)
        b = mongo.call(method, path, who, **kwargs)
        statuses[label] = b[0]
        if options.startswith("token:"):
            name = options.split(":", 1)[1]
            sql.tokens[name] = a[1].get("access_token")
            mongo.tokens[name] = b[1].get("access_token")
        expected, got = (a[0], normalize(a[1])), (b[0], normalize(b[1]))
        if options == "unordered" and isinstance(a[1], list):
            key = lambda x: x.get("id", 0)
            expected = (a[0], sorted(expected[1], key=key))
            got = (b[0], sorted(got[1], key=key))
        if options == "legacy_events" and a[0] == 200:
            # Lab 1 returned the raw TEXT column, which for Part A events was
            # a JSON string; Lab 2 returns the human-readable description.
            import json as _json
            for row in expected[1]:
                try:
                    row["eligibility"] = _json.loads(row["eligibility"])["description"]
                except (ValueError, TypeError, KeyError):
                    pass
        if expected != got:
            mismatches.append(f"{label}: {method} {path}\n  lab1 {expected}\n  mongo {got}")
    assert not mismatches, f"{len(mismatches)} differences:\n" + "\n".join(mismatches)

    # Guard against a vacuous pass (e.g. every call failing the same way).
    from collections import Counter
    by_status = Counter(statuses.values())
    successes = sum(n for code, n in by_status.items() if code < 300)
    print(f"\nPARITY {len(SCENARIO)} calls identical; status codes: {dict(sorted(by_status.items()))}")
    assert successes >= 70, by_status
    assert statuses["apply job 1"] == 201
    assert statuses["register eligible"] == 201
    assert statuses["register ineligible major"] == 403
    assert statuses["review other's applicant"] == 403
    assert 500 not in by_status
