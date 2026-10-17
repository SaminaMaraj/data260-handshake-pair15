"""
Authorization tests for preferences and saved items.

Proves one student cannot read, modify, save for, or delete another
student's data. Uses an isolated in-memory SQLite database, so the
Pair 15 MySQL data is never touched.

Run from the backend folder:
    python -m pytest tests/test_preferences_authorization.py -q
"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault(
    "JWT_SECRET_KEY", "isolated-preferences-test-key-not-for-production"
)

from app.auth import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.additional import SavedItem, StudentPreference
from app.models.core import Company, Job, Student, User


@compiles(BigInteger, "sqlite")
def sqlite_bigint(element, compiler, **kwargs):
    return "INTEGER"


STUDENT_A = 3
STUDENT_B = 4
COMPANY = 1


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    with Session(engine) as db:
        users = [
            User(id=COMPANY, email="company@example.com", role="company",
                 password_hash="unused", is_active=True),
            User(id=STUDENT_A, email="a@example.com", role="student",
                 password_hash="unused", is_active=True),
            User(id=STUDENT_B, email="b@example.com", role="student",
                 password_hash="unused", is_active=True),
        ]
        db.add_all(users)
        db.flush()
        db.add_all([
            Company(user_id=COMPANY, company_name="Host"),
            Student(user_id=STUDENT_A, full_name="Student A",
                    major="Data Science", college_name="SJSU"),
            Student(user_id=STUDENT_B, full_name="Student B",
                    major="History", college_name="SJSU"),
        ])
        db.flush()
        db.add_all([
            Job(id=1, company_id=COMPANY, title="Data Analyst",
                posting_date=date.today(),
                deadline=date.today() + timedelta(days=30),
                location="Sunnyvale", description="Test job",
                category="internship", is_remote=False),
            Job(id=2, company_id=COMPANY, title="Software Engineer",
                posting_date=date.today(),
                deadline=date.today() + timedelta(days=30),
                location="Cupertino", description="Test job",
                category="internship", is_remote=False),
        ])
        db.flush()
        # Student B already has preferences and one saved job.
        db.add(StudentPreference(student_id=STUDENT_B,
                                 preferred_city="Palo Alto",
                                 remote_only=False))
        db.add(SavedItem(id=10, student_id=STUDENT_B, job_id=1))
        db.commit()

        tokens = {
            user.id: {"Authorization": "Bearer " + create_access_token(user)}
            for user in users
        }

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app) as client:
                yield client, tokens, db
        finally:
            app.dependency_overrides.pop(get_db, None)

    engine.dispose()


def b_state(db):
    db.expire_all()
    preference = db.get(StudentPreference, STUDENT_B)
    items = db.scalars(
        select(SavedItem).where(SavedItem.student_id == STUDENT_B)
    ).all()
    return preference.preferred_city, sorted(item.id for item in items)


def test_routes_require_login(api):
    client, _, _ = api
    for method, path, body in [
        ("GET", f"/students/{STUDENT_B}/preferences", None),
        ("PUT", f"/students/{STUDENT_B}/preferences", {"preferred_city": "X"}),
        ("POST", "/saved-items", {"student_id": STUDENT_B, "job_id": 2}),
        ("GET", f"/saved-items/student/{STUDENT_B}", None),
        ("DELETE", "/saved-items/10", None),
    ]:
        response = client.request(method, path, json=body)
        assert response.status_code == 401, (method, path, response.text)


def test_company_account_is_rejected(api):
    client, tokens, _ = api
    response = client.get(
        f"/saved-items/student/{STUDENT_B}", headers=tokens[COMPANY]
    )
    assert response.status_code == 403


def test_student_cannot_read_another_students_data(api):
    client, tokens, _ = api
    a = tokens[STUDENT_A]

    response = client.get(f"/students/{STUDENT_B}/preferences", headers=a)
    assert response.status_code == 403

    response = client.get(f"/saved-items/student/{STUDENT_B}", headers=a)
    assert response.status_code == 403


def test_student_cannot_modify_another_students_preferences(api):
    client, tokens, db = api
    before = b_state(db)

    response = client.put(
        f"/students/{STUDENT_B}/preferences",
        json={"preferred_city": "Cupertino"},
        headers=tokens[STUDENT_A],
    )
    assert response.status_code == 403
    assert b_state(db) == before


def test_student_cannot_save_for_another_student(api):
    client, tokens, db = api
    before = b_state(db)

    response = client.post(
        "/saved-items",
        json={"student_id": STUDENT_B, "job_id": 2},
        headers=tokens[STUDENT_A],
    )
    assert response.status_code == 403
    assert b_state(db) == before


def test_student_cannot_delete_another_students_saved_item(api):
    client, tokens, db = api
    before = b_state(db)

    response = client.delete("/saved-items/10", headers=tokens[STUDENT_A])
    assert response.status_code == 403
    assert b_state(db) == before


def test_student_can_manage_own_data(api):
    client, tokens, db = api
    b = tokens[STUDENT_B]

    response = client.put(
        f"/students/{STUDENT_B}/preferences",
        json={"preferred_city": "Cupertino"},
        headers=b,
    )
    assert response.status_code == 200, response.text
    assert response.json()["preferred_city"] == "Cupertino"

    response = client.get(f"/students/{STUDENT_B}/preferences", headers=b)
    assert response.status_code == 200

    response = client.post(
        "/saved-items", json={"student_id": STUDENT_B, "job_id": 2}, headers=b
    )
    assert response.status_code == 201, response.text
    new_id = response.json()["id"]
    assert response.json()["student_id"] == STUDENT_B

    response = client.get(f"/saved-items/student/{STUDENT_B}", headers=b)
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {10, new_id}

    response = client.delete(f"/saved-items/{new_id}", headers=b)
    assert response.status_code == 204
    assert b_state(db) == ("Cupertino", [10])
