"""Add only the assistant approval table; preserves all existing tables/data.

Run from the project root: PYTHONPATH=backend python backend/scripts/init_assistant_pending.py
"""
from app.database import engine
from app.models import core, additional  # Register FK targets.
from app.assistant.pending import PendingAction

if __name__ == '__main__':
    PendingAction.__table__.create(engine, checkfirst=True)
    print('Assistant pending-action table is ready.')
