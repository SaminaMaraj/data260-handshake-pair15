"""Lab 2 S5: the MongoDB assistant tools return what the Lab 1 SQL tools returned.

Builds the Pair 15 seed (random_state = 15) once in SQLite, migrates it into
a throwaway MongoDB database with scripts/migrate_to_mongo.py, then calls
every read-only tool with the same arguments on both and compares the
result strings. The model therefore sees the same data in Lab 2.

The one intended difference: search_events returns eligibility as the
structured {description, majors, colleges} object instead of Lab 1's raw
TEXT column; the test compares the description inside it.

Needs MongoDB (MONGO_URL); skipped if unreachable.
Run from backend/:  python -m pytest tests/test_tool_parity.py -q
"""
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("JWT_SECRET_KEY", "tool-parity-test-key-not-for-production-01")

import pytest

NEXT_MONTH_START = (date.today().replace(day=1) + timedelta(days=32)).replace(day=1)
NEXT_MONTH_END = (NEXT_MONTH_START + timedelta(days=32)).replace(day=1) - timedelta(days=1)

CALLS = [
    ("get_student_preferences", {"student_id": 1}),
    ("get_student_preferences", {"student_id": 99999}),
    ("search_jobs", {"city": "Sunnyvale", "category": "internship",
                     "skill": "Python,SQL", "salary_min": 70000}),
    ("search_jobs", {"category": "internship", "remote_only": True,
                     "skill": "Python, R, SQL, machine learning, data analysis"}),
    ("search_jobs", {"title": "analyst"}),
    ("search_jobs", {"company": "Pair 15 Company 0018"}),
    ("search_jobs", {"company": "Nonexistent Labs"}),
    ("search_jobs", {"category": "gig"}),
    ("search_jobs", {"deadline_before": "not-a-date"}),
    ("search_jobs", {"city": "Palo Alto", "deadline_before":
                     (date.today() + timedelta(days=60)).isoformat()}),
    ("rank_jobs", {"job_ids": [51, 25, 74, 166, 291, 211, 206, 264], "limit": 5}),
    ("rank_jobs", {"job_ids": [1, 2, 99999], "limit": 3}),
    ("rank_jobs", {"job_ids": []}),
    ("get_job_details", {"job_id": 42}),
    ("get_job_details", {"job_id": 99999}),
    ("search_events", {"major": "Computer Science",
                       "date_from": NEXT_MONTH_START.isoformat(),
                       "date_to": NEXT_MONTH_END.isoformat()}),
    ("search_events", {"city": "Cupertino"}),
    ("search_events", {"name": "Resume"}),
    ("search_events", {"name": "No Such Event"}),
    ("search_events", {"date_from": "13/45/2026"}),
]


@pytest.fixture(scope="module")
def tool_pair():
    from services.common import mongo
    try:
        mongo.client().admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    os.environ["MONGO_DB"] = f"p15_tools_{uuid.uuid4().hex[:8]}"
    from scripts.migrate_to_mongo import migrate, run_seed_into_sqlite
    sql_url = run_seed_into_sqlite()
    assert migrate(sql_url, drop=True) == 0
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.assistant.tools as lab1_tools
    lab1_tools.SessionLocal = sessionmaker(bind=create_engine(sql_url))
    from services.assistant.agent import tools as lab2_tools
    yield lab1_tools, lab2_tools
    mongo.client().drop_database(os.environ["MONGO_DB"])


def comparable(tool, text):
    """Parse JSON results; for events compare the eligibility description."""
    if tool == "search_events" and text.startswith("["):
        rows = json.loads(text)
        for row in rows:
            e = row["eligibility"]
            if isinstance(e, dict):
                row["eligibility"] = e["description"]
            else:
                try:
                    row["eligibility"] = json.loads(e)["description"]
                except (ValueError, TypeError, KeyError):
                    pass
        return rows
    return text


@pytest.mark.parametrize("tool,args", CALLS, ids=[f"{t}-{i}" for i, (t, _) in enumerate(CALLS)])
def test_tool_returns_same_result(tool_pair, tool, args):
    lab1, lab2 = tool_pair
    expected = lab1.execute_tool(tool, dict(args))
    got = lab2.execute_tool(tool, dict(args))
    assert comparable(tool, got) == comparable(tool, expected)


def test_results_are_not_all_empty(tool_pair):
    _, lab2 = tool_pair
    found = [lab2.execute_tool(t, dict(a)) for t, a in CALLS]
    assert sum(r.startswith(("JOB_IDS", "{", "[")) for r in found) >= 10
