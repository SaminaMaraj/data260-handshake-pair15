"""Lab 2 S1: the six services together expose exactly the Lab 1 API.

Proves that
  1. every Lab 1 route (method + path) is served by exactly one service,
  2. the only routes Lab 1 did not have are the declared Lab 2 additions,
  3. each route lives in the service that owns its path prefix,
  4. each service answers /health and stamps responses with X-Service.

Behavior of the routes is proven by tests/test_mongo_parity.py.
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

from app.main import app as monolith
from services.common.app_factory import build_service_app
from services.common.routing import SERVICE_PORTS, owner_of

HEALTH = {"/health", "/health/db"}
MONOLITH_ONLY = {"/", "/health/db"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
LAB2_ADDITIONS = {
    ("POST", "/users/logout"),            # revoke the server session
    ("POST", "/assistant/session/end"),   # memory layer 3 -> consolidation consumer
    ("GET", "/assistant/memory"),         # learned memory for the UI
}


@pytest.fixture(autouse=True)
def in_memory_mongo(monkeypatch):
    """These checks need no real data: use the in-process fake, for this
    module only (other test modules use a real MongoDB)."""
    monkeypatch.setenv("MONGO_URL", "mongomock://")


def api_routes(app):
    """Set of (METHOD, path) pairs the app serves, from its OpenAPI spec."""
    return {(m.upper(), path)
            for path, ops in app.openapi()["paths"].items()
            for m in ops if m in HTTP_METHODS}


@pytest.fixture(scope="module")
def services():
    return {name: build_service_app(name) for name in SERVICE_PORTS}


def lab1_routes():
    return {p for p in api_routes(monolith) if p[1] not in MONOLITH_ONLY}


def test_split_is_not_vacuous(services):
    assert len(lab1_routes()) >= 50
    for name, svc in services.items():
        assert {p for p in api_routes(svc) if p[1] not in HEALTH}, f"{name} serves no routes"


def test_every_lab1_route_is_owned_by_exactly_one_service(services):
    served = {}
    for name, svc in services.items():
        for pair in api_routes(svc):
            if pair[1] in HEALTH:
                continue
            assert pair not in served, f"{pair} served by {served[pair]} and {name}"
            served[pair] = name
    missing = lab1_routes() - set(served)
    extra = set(served) - lab1_routes() - LAB2_ADDITIONS
    assert not missing, f"Lab 1 routes lost in the split: {sorted(missing)}"
    assert not extra, f"Undeclared new routes: {sorted(extra)}"
    for (_method, path), name in served.items():
        assert owner_of(path) == name, f"{path} mounted in {name}, owned by {owner_of(path)}"


def test_longest_prefix_ownership():
    assert owner_of("/companies/me/jobs") == "job"
    assert owner_of("/companies/me/applications") == "application"
    assert owner_of("/companies/{user_id}") == "company"
    assert owner_of("/events/search") == "event"
    assert owner_of("/students/me/saved-jobs") == "student"
    assert owner_of("/jobsearch") is None  # a prefix must end at "/"


@pytest.mark.parametrize("name", list(SERVICE_PORTS))
def test_health_and_service_header(name):
    with TestClient(build_service_app(name)) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["service"] == f"p15-{name}"
        assert res.headers["X-Service"] == f"p15-{name}"
        assert client.get("/health/db").status_code == 200


def test_route_lives_only_on_its_owner(services):
    with TestClient(services["company"]) as company:
        assert company.get("/companies/me/jobs").status_code in (404, 422)
    with TestClient(services["job"]) as job:
        assert job.get("/companies/me/jobs").status_code == 401  # exists, needs login
