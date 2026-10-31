"""Lab 2 S1: the six services together expose exactly the Lab 1 API.

Proves that
  1. every Lab 1 route (method + path) is served by exactly one service,
  2. no service exposes a route the monolith did not have,
  3. static paths still win over path parameters inside each service
     (e.g. /events/search is not swallowed by /events/{event_id}),
  4. each service answers /health and stamps responses with X-Service,
  5. a token issued by one service is accepted by another, and a route is
     reachable only on the service that owns it.

Routes are read from each app's OpenAPI spec (no Lab 1 route is hidden
from the schema), which works across FastAPI versions.

Run from backend/:  python -m pytest tests/test_service_split.py -q
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "isolated-service-split-test-key-not-for-prod")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app as monolith
from services.common.app_factory import build_service_app
from services.common.routing import SERVICE_PORTS, owner_of

HEALTH = {"/health", "/health/db"}
MONOLITH_ONLY = {"/", "/health/db"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@compiles(BigInteger, "sqlite")
def _sqlite_bigint(element, compiler, **kwargs):
    return "INTEGER"


def api_routes(app):
    """Set of (METHOD, path) pairs the app serves, from its OpenAPI spec."""
    return {(m.upper(), path)
            for path, ops in app.openapi()["paths"].items()
            for m in ops if m in HTTP_METHODS}


@pytest.fixture(scope="module")
def services():
    return {name: build_service_app(name) for name in SERVICE_PORTS}


def test_split_is_not_vacuous(services):
    lab1 = api_routes(monolith) - {(m, p) for m, p in api_routes(monolith) if p in MONOLITH_ONLY}
    assert len(lab1) >= 50, len(lab1)
    for name, svc in services.items():
        own = {p for p in api_routes(svc) if p[1] not in HEALTH}
        assert own, f"{name} serves no routes"


def test_every_lab1_route_is_owned_by_exactly_one_service(services):
    lab1 = {p for p in api_routes(monolith) if p[1] not in MONOLITH_ONLY}
    served = {}
    for name, svc in services.items():
        for pair in api_routes(svc):
            if pair[1] in HEALTH:
                continue
            assert pair not in served, f"{pair} served by {served[pair]} and {name}"
            served[pair] = name
    missing = lab1 - set(served)
    extra = set(served) - lab1
    assert not missing, f"Lab 1 routes lost in the split: {sorted(missing)}"
    assert not extra, f"Routes not in Lab 1: {sorted(extra)}"
    for (_method, path), name in served.items():
        assert owner_of(path) == name


def test_longest_prefix_ownership():
    assert owner_of("/companies/me/jobs") == "job"
    assert owner_of("/companies/me/applications") == "application"
    assert owner_of("/companies/{user_id}") == "company"
    assert owner_of("/events/search") == "event"
    assert owner_of("/students/me/saved-jobs") == "student"
    assert owner_of("/jobsearch") is None  # a prefix must end at "/"


@pytest.mark.parametrize("name", list(SERVICE_PORTS))
def test_health_and_service_header(name):
    client = TestClient(build_service_app(name))
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["service"] == f"p15-{name}"
    assert res.headers["X-Service"] == f"p15-{name}"
    assert client.get("/health/db").status_code == 200


# ---- end-to-end across services on one shared (test) database ----------

@pytest.fixture(scope="module")
def shared_db(services):
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

    for svc in services.values():
        svc.dependency_overrides[get_db] = override
    yield {name: TestClient(svc) for name, svc in services.items()}
    for svc in services.values():
        svc.dependency_overrides.clear()


@pytest.mark.parametrize("service,path", [
    ("event", "/events/search"),          # vs /events/{event_id}
    ("job", "/jobs/search"),              # vs /jobs/{job_id}
    ("student", "/students/search"),      # vs /students/{user_id}
    ("student", "/students/me/preferences"),  # vs /students/{student_id}/preferences
])
def test_static_paths_answer_like_the_monolith(shared_db, service, path):
    # If /{id} were registered first, the service would answer 422/404
    # where the Lab 1 monolith does not. Same status code = same route.
    mono = TestClient(monolith)
    monolith.dependency_overrides[get_db] = (
        shared_db[service].app.dependency_overrides[get_db])
    try:
        expected = mono.get(path).status_code
    finally:
        monolith.dependency_overrides.clear()
    got = shared_db[service].get(path).status_code
    assert got == expected, f"{path}: service {got}, monolith {expected}"
    assert got not in (404, 422)


def test_token_from_student_service_works_on_job_service(shared_db):
    student_svc, job_svc = shared_db["student"], shared_db["job"]
    reg = student_svc.post("/users/register", json={
        "email": "split-co@example.com", "password": "Sup3rSecret!pw",
        "role": "company", "name": "Split Test Co", "location": "Sunnyvale"})
    assert reg.status_code == 201, reg.text
    login = student_svc.post("/users/login", json={
        "email": "split-co@example.com", "password": "Sup3rSecret!pw"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    # Owned by the job service: works there ...
    mine = job_svc.get("/companies/me/jobs", headers=auth)
    assert mine.status_code == 200, mine.text
    assert mine.headers["X-Service"] == "p15-job"
    # ... and does not exist on the company service.
    assert shared_db["company"].get("/companies/me/jobs", headers=auth).status_code in (404, 422)
