"""Lab 2 Part 3: MongoDB security and integrity guarantees.

  * passwords are bcrypt hashes, never stored or returned in plain text
  * every JWT is tied to a server session; logout revokes it at once
  * an expired session is rejected even before MongoDB's TTL sweep deletes it
  * a session cannot be reused by a different user id (tampered token)
  * TTL indexes exist on sessions and pending_actions
  * unique indexes stop duplicate applications / registrations / saved items,
    which is what makes a replayed Kafka message harmless

Run from backend/:  python -m pytest tests/test_mongo_security.py -q
"""
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET_KEY", "security-test-key-not-for-production-0123456")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")

import jwt
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError


@pytest.fixture(scope="module")
def env():
    from services.common import mongo
    try:
        mongo.client().admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    name = f"p15_security_{uuid.uuid4().hex[:8]}"
    os.environ["MONGO_DB"] = name
    from services.common.app_factory import build_service_app
    student = TestClient(build_service_app("student"))
    student.__enter__()
    student.post("/users/register", json={"email": "sec@p15.dev",
                                          "password": "StrongPass1!", "role": "student"})
    yield student, mongo.database()
    student.__exit__(None, None, None)
    mongo.client().drop_database(name)


def login(client):
    res = client.post("/users/login", json={"email": "sec@p15.dev", "password": "StrongPass1!"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_password_is_bcrypt_hashed(env):
    _, db = env
    user = db.users.find_one({"email": "sec@p15.dev"})
    assert user["password_hash"].startswith("$2b$")
    assert "StrongPass1!" not in str(user)


def test_login_creates_session_and_logout_revokes_it(env):
    client, db = env
    token = login(client)
    sid = jwt.decode(token, options={"verify_signature": False})["sid"]
    session = db.sessions.find_one({"_id": sid})
    assert session is not None and session["expires_at"] > session["created_at"]
    assert client.get("/users/me", headers=auth(token)).status_code == 200

    assert client.post("/users/logout", headers=auth(token)).status_code == 204
    assert db.sessions.find_one({"_id": sid}) is None
    # Same, still-unexpired JWT is now rejected.
    assert client.get("/users/me", headers=auth(token)).status_code == 401


def test_two_logins_are_independent_sessions(env):
    client, _ = env
    t1, t2 = login(client), login(client)
    client.post("/users/logout", headers=auth(t1))
    assert client.get("/users/me", headers=auth(t1)).status_code == 401
    assert client.get("/users/me", headers=auth(t2)).status_code == 200


def test_expired_session_rejected_before_ttl_sweep(env):
    client, db = env
    token = login(client)
    sid = jwt.decode(token, options={"verify_signature": False})["sid"]
    from services.common.mongo import utcnow
    db.sessions.update_one({"_id": sid}, {"$set": {"expires_at": utcnow() - timedelta(seconds=1)}})
    assert client.get("/users/me", headers=auth(token)).status_code == 401


def test_session_bound_to_its_user(env):
    client, _ = env
    token = login(client)
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode({**claims, "sub": "999"}, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
    assert client.get("/users/me", headers=auth(forged)).status_code == 401


def test_ttl_indexes(env):
    _, db = env
    for collection in ("sessions", "pending_actions"):
        ttl = [i for i in db[collection].list_indexes() if "expireAfterSeconds" in i]
        assert ttl and ttl[0]["key"] == {"expires_at": 1}, collection


def test_unique_indexes_block_duplicates(env):
    _, db = env
    db.applications.insert_one({"_id": 9001, "job_id": 1, "student_id": 1})
    with pytest.raises(DuplicateKeyError):          # same id (replayed message)
        db.applications.insert_one({"_id": 9001, "job_id": 2, "student_id": 1})
    with pytest.raises(DuplicateKeyError):          # same (job, student)
        db.applications.insert_one({"_id": 9002, "job_id": 1, "student_id": 1})
    db.event_registrations.insert_one({"_id": 1, "event_id": 5, "student_id": 1})
    with pytest.raises(DuplicateKeyError):
        db.event_registrations.insert_one({"_id": 2, "event_id": 5, "student_id": 1})
    db.saved_items.insert_one({"_id": 1, "student_id": 1, "job_id": 7, "event_id": None})
    db.saved_items.insert_one({"_id": 2, "student_id": 1, "job_id": None, "event_id": 7})
    with pytest.raises(DuplicateKeyError):
        db.saved_items.insert_one({"_id": 3, "student_id": 1, "job_id": 7, "event_id": None})
