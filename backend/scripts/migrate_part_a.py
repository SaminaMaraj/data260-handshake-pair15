"""Idempotent additive migration; preserves all existing tables and rows."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, text
from app.database import engine

if __name__ == '__main__':
    with engine.begin() as connection:
        if 'education' not in {c['name'] for c in inspect(connection).get_columns('students')}:
            connection.execute(text('ALTER TABLE students ADD COLUMN education TEXT NULL'))
            print('Added nullable students.education; no existing records removed.')
        else:
            print('students.education already exists; no changes needed.')
