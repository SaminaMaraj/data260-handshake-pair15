"""
Tests for saved event preferences (gap 3).

Uses the isolated in-memory SQLite API fixture from
test_preferences_authorization.py; the Pair 15 MySQL data is never touched.

Run from the backend folder:
    python -m pytest tests/test_event_preferences.py -q
"""
import json

from sqlalchemy import create_engine, text

from app.assistant import tools
from app.models.additional import StudentPreference
from tests.test_preferences_authorization import STUDENT_A, STUDENT_B, api  # noqa: F401

EVENT_PREFS = {"preferred_event_majors_json": ["History"],
               "preferred_event_city": "Cupertino"}


def test_me_route_saves_and_returns_event_preferences(api):
    client, tokens, db = api
    body = {"preferred_city": "Palo Alto", **EVENT_PREFS}
    response = client.put("/students/me/preferences", json=body, headers=tokens[STUDENT_B])
    assert response.status_code == 200, response.text
    saved = client.get("/students/me/preferences", headers=tokens[STUDENT_B]).json()
    assert saved["preferred_event_majors_json"] == ["History"]
    assert saved["preferred_event_city"] == "Cupertino"


def test_id_route_saves_event_preferences(api):
    client, tokens, db = api
    response = client.put(f"/students/{STUDENT_B}/preferences",
                          json=EVENT_PREFS, headers=tokens[STUDENT_B])
    assert response.status_code == 200, response.text
    assert response.json()["preferred_event_city"] == "Cupertino"


def test_job_only_update_keeps_saved_event_preferences(api):
    """The current frontend form may omit event fields; they must survive."""
    client, tokens, db = api
    b = tokens[STUDENT_B]
    client.put("/students/me/preferences", json=EVENT_PREFS, headers=b)
    client.put("/students/me/preferences", json={"preferred_city": "Sunnyvale"}, headers=b)
    client.put(f"/students/{STUDENT_B}/preferences", json={"preferred_city": "Sunnyvale"}, headers=b)
    db.expire_all()
    row = db.get(StudentPreference, STUDENT_B)
    assert row.preferred_city == "Sunnyvale"
    assert row.preferred_event_majors_json == ["History"]
    assert row.preferred_event_city == "Cupertino"


def test_event_preferences_can_be_cleared_explicitly(api):
    client, tokens, db = api
    b = tokens[STUDENT_B]
    client.put("/students/me/preferences", json=EVENT_PREFS, headers=b)
    clear = {"preferred_event_majors_json": None, "preferred_event_city": None}
    assert client.put("/students/me/preferences", json=clear, headers=b).status_code == 200
    db.expire_all()
    assert db.get(StudentPreference, STUDENT_B).preferred_event_city is None


def test_event_city_length_is_validated(api):
    client, tokens, _ = api
    response = client.put("/students/me/preferences",
                          json={"preferred_event_city": "x" * 101},
                          headers=tokens[STUDENT_B])
    assert response.status_code == 422


def test_other_student_cannot_change_event_preferences(api):
    client, tokens, db = api
    response = client.put(f"/students/{STUDENT_B}/preferences",
                          json=EVENT_PREFS, headers=tokens[STUDENT_A])
    assert response.status_code == 403
    db.expire_all()
    assert db.get(StudentPreference, STUDENT_B).preferred_event_city is None


def test_tool_returns_job_and_event_preferences(api, monkeypatch):
    client, tokens, db = api
    client.put("/students/me/preferences",
               json={"preferred_city": "Palo Alto", **EVENT_PREFS}, headers=tokens[STUDENT_B])
    monkeypatch.setattr(tools, "SessionLocal", lambda: _NoClose(db))
    data = json.loads(tools.get_student_preferences(STUDENT_B))
    assert data["preferred_city"] == "Palo Alto"
    assert data["event_preferences"] == {"preferred_majors": ["History"],
                                         "preferred_city": "Cupertino"}


class _NoClose:
    """Lets the tool use the fixture session without closing it."""
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


def test_migration_adds_columns_and_backfills_once(tmp_path):
    import scripts.migrate_event_preferences as migration

    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE students (user_id INTEGER PRIMARY KEY, major TEXT)"))
        c.execute(text("CREATE TABLE student_preferences (student_id INTEGER PRIMARY KEY, "
                       "preferred_city VARCHAR(100))"))
        c.execute(text("INSERT INTO students VALUES (1, 'History'), (2, NULL)"))
        c.execute(text("INSERT INTO student_preferences VALUES (1, 'Sunnyvale'), (2, 'Cupertino')"))
    with engine.begin() as c:
        migration.migrate(c)
    with engine.begin() as c:
        c.execute(text("UPDATE student_preferences SET preferred_event_city = 'Edited' "
                       "WHERE student_id = 1"))
        migration.migrate(c)  # second run must not overwrite edits
        rows = c.execute(text("SELECT student_id, preferred_event_majors_json, "
                              "preferred_event_city FROM student_preferences "
                              "ORDER BY student_id")).all()
    assert json.loads(rows[0][1]) == ["History"] and rows[0][2] == "Edited"
    assert rows[1][1] is None and rows[1][2] == "Cupertino"
    with engine.begin() as c:
        # Existing job preference data is preserved by the migration.
        assert c.execute(text("SELECT student_id, preferred_city FROM student_preferences "
                              "ORDER BY student_id")).all() == [(1, "Sunnyvale"), (2, "Cupertino")]
        migration.rollback(c)
    with engine.begin() as c:
        columns = [row[1] for row in c.execute(text("PRAGMA table_info(student_preferences)"))]
        rows = c.execute(text("SELECT * FROM student_preferences ORDER BY student_id")).all()
    # Rollback removes only the two new columns and keeps every row.
    assert columns == ["student_id", "preferred_city"]
    assert rows == [(1, "Sunnyvale"), (2, "Cupertino")]
    engine.dispose()
