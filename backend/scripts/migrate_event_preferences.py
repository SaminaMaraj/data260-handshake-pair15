"""Idempotent additive migration for saved event preferences.

Adds two nullable columns to student_preferences and fills them only for
rows where both are still empty. Seed values are the student's own major
and the row's preferred_city; students can change them through
PUT /students/me/preferences. No rows or columns are removed.

Run from the backend folder:
    python scripts/migrate_event_preferences.py          # apply
    python scripts/migrate_event_preferences.py --down   # undo (drops only the two new columns)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text

from app.database import engine

COLUMNS = {
    "preferred_event_majors_json": "JSON NULL",
    "preferred_event_city": "VARCHAR(100) NULL",
}


def migrate(connection) -> None:
    existing = {c["name"] for c in inspect(connection).get_columns("student_preferences")}
    for name, definition in COLUMNS.items():
        if name in existing:
            print(f"student_preferences.{name} already exists; no change.")
        else:
            connection.execute(text(
                f"ALTER TABLE student_preferences ADD COLUMN {name} {definition}"))
            print(f"Added nullable student_preferences.{name}.")

    rows = connection.execute(text(
        "SELECT p.student_id, s.major, p.preferred_city "
        "FROM student_preferences p JOIN students s ON s.user_id = p.student_id "
        "WHERE p.preferred_event_majors_json IS NULL AND p.preferred_event_city IS NULL"
    )).all()
    for student_id, major, city in rows:
        connection.execute(
            text("UPDATE student_preferences SET preferred_event_majors_json = :majors, "
                 "preferred_event_city = :city WHERE student_id = :id"),
            {"majors": json.dumps([major]) if major else None, "city": city, "id": student_id},
        )
    print(f"Filled event preferences for {len(rows)} rows that had none.")


def rollback(connection) -> None:
    existing = {c["name"] for c in inspect(connection).get_columns("student_preferences")}
    for name in COLUMNS:
        if name in existing:
            connection.execute(text(f"ALTER TABLE student_preferences DROP COLUMN {name}"))
            print(f"Dropped student_preferences.{name}.")
        else:
            print(f"student_preferences.{name} does not exist; no change.")


if __name__ == "__main__":
    with engine.begin() as connection:
        if "--down" in sys.argv[1:]:
            rollback(connection)
        else:
            migrate(connection)
