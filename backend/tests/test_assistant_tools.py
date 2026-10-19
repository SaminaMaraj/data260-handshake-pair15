"""
Offline tests for the assistant tool changes and the chain-loss measure.
Uses an isolated in-memory SQLite database; no Ollama or MySQL needed.

Run from the backend folder:
    python -m pytest tests/test_assistant_tools.py -q
"""
import json
import os
import re
import sys
from datetime import date, time, timedelta
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "isolated-tools-test-key-not-for-production")

from app.assistant import tools
from app.assistant.reliability_run import CHAIN_RULES, PROMPTS, chain_lost
from app.database import Base
from app.models.additional import Event, StudentPreference
from app.models.core import Company, Student, User


@compiles(BigInteger, "sqlite")
def sqlite_bigint(element, compiler, **kwargs):
    return "INTEGER"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        session.add_all([
            User(id=1, email="c@example.com", role="company",
                 password_hash="x", is_active=True),
            User(id=2, email="s@example.com", role="student",
                 password_hash="x", is_active=True),
            User(id=3, email="n@example.com", role="student",
                 password_hash="x", is_active=True),
        ])
        session.flush()
        session.add_all([
            Company(user_id=1, company_name="Host"),
            Student(user_id=2, full_name="With Prefs"),
            Student(user_id=3, full_name="No Prefs"),
        ])
        session.flush()
        soon = date.today() + timedelta(days=5)

        def event(name, eligibility):
            return Event(company_id=1, event_name=name, description="d",
                         event_date=soon, event_time=time(12), location="Sunnyvale",
                         eligibility=eligibility)

        session.add_all([
            event("CS Day", "Computer Science students"),
            event("History Talk", json.dumps({"version": 1, "description": "Open",
                                              "majors": ["History"], "colleges": []})),
            event("Open Fair", "All enrolled students"),
        ])
        session.add(StudentPreference(student_id=2, preferred_city="Sunnyvale",
                                      preferred_category="internship",
                                      preferred_skills_json=["Python"], remote_only=False))
        session.commit()
    monkeypatch.setattr(tools, "SessionLocal", Session)
    yield Session
    engine.dispose()


def names(result: str) -> list[str]:
    return [event["event_name"] for event in json.loads(result)]


# ---- Gap 2: typed major filter on search_events

def test_major_filter_matches_text_eligibility(db):
    assert names(tools.search_events(major="computer science")) == ["CS Day"]


def test_major_filter_matches_json_eligibility(db):
    assert names(tools.search_events(major="History")) == ["History Talk"]


def test_major_filter_no_match_returns_message(db):
    assert tools.search_events(major="Chemistry") == "No matching upcoming events were found."


def test_major_filter_rejects_bad_input_without_raising(db):
    assert tools.search_events(major=123).startswith("major must be text")
    assert tools.search_events(major="x" * 101).startswith("major must be text")


def test_without_major_all_events_returned(db):
    assert len(json.loads(tools.search_events())) == 3


def test_search_events_schema_documents_major():
    schema = next(t for t in tools.TOOL_SCHEMAS if t["function"]["name"] == "search_events")
    major = schema["function"]["parameters"]["properties"]["major"]
    assert major["type"] == "string" and major["description"]


def test_execute_tool_passes_major(db):
    assert names(tools.execute_tool("search_events", {"major": "History"})) == ["History Talk"]


# ---- Gap 3: preferences tool (event preferences are in test_event_preferences.py)

def test_preferences_no_data_message(db):
    assert tools.get_student_preferences(3) == "No preferences are saved for this student."


def test_preferences_returns_job_preferences(db):
    data = json.loads(tools.get_student_preferences(2))
    assert data["preferred_city"] == "Sunnyvale" and data["preferred_skills"] == ["Python"]
    assert data["event_preferences"] == {"preferred_majors": None, "preferred_city": None}


# ---- Gap 1: generic skills guidance, no test phrases in production code

def test_search_jobs_schema_guides_fields_of_work_to_skill():
    schema = next(t for t in tools.TOOL_SCHEMAS if t["function"]["name"] == "search_jobs")
    props = schema["function"]["parameters"]["properties"]
    assert "field of work" in schema["function"]["description"]
    assert "field of work" in props["skill"]["description"]
    assert "actual job title" in props["title"]["description"]


def test_no_required_test_phrases_in_production_code():
    root = Path(__file__).resolve().parents[1] / "app"
    production = [root / "assistant" / name for name in
                  ("tools.py", "loop.py", "confirm.py", "client.py")]
    production.append(root / "routers" / "assistant.py")
    text = "\n".join(path.read_text().lower() for path in production)
    # Exact test requests must not appear anywhere in production code.
    for phrase in ("data science", "computer science", "nonexistent labs",
                   "higher paying"):
        assert phrase not in text, phrase
    # No code branches on the user's message text.
    assert not re.search(r"in\s+(request_text|user_message)", text)


# ---- Gap 4: chain-loss measurement

def tool_call(name, args):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def tool_result(name, content):
    return {"role": "tool", "tool_name": name, "content": content}


SEARCH = tool_result("search_jobs",
                     'JOB_IDS: [5, 9]\nJOBS: [{"job_id": 5}, {"job_id": 9}]')


def test_chain_rules_refer_to_real_prompts():
    assert set(CHAIN_RULES) <= set(PROMPTS)


def test_single_step_prompt_never_counts():
    assert chain_lost(None, [], [tool_call("search_jobs", {}), SEARCH]) is False


def test_text_only_turn_is_not_double_counted():
    assert chain_lost("preferences_then_search", [], [{"role": "assistant", "content": "hi"}]) is False


def test_preferences_without_search_is_lost():
    turn = [tool_call("get_student_preferences", {}),
            tool_result("get_student_preferences", "{}"),
            {"role": "assistant", "content": "done"}]
    assert chain_lost("preferences_then_search", [], turn) is True


def test_preferences_then_search_is_complete():
    turn = [tool_call("get_student_preferences", {}),
            tool_result("get_student_preferences", "{}"),
            tool_call("search_jobs", {"city": "Sunnyvale"}), SEARCH]
    assert chain_lost("preferences_then_search", [], turn) is False


def test_search_without_preferences_is_lost():
    turn = [tool_call("search_jobs", {}), SEARCH]
    assert chain_lost("preferences_then_search", [], turn) is True


def test_details_with_previous_id_is_complete():
    turn = [tool_call("get_job_details", {"job_id": 9}),
            tool_result("get_job_details", '{"id": 9}')]
    assert chain_lost("details_from_previous_results", [SEARCH], turn) is False


def test_details_with_unrelated_id_is_lost():
    turn = [tool_call("get_job_details", {"job_id": 123}),
            tool_result("get_job_details", '{"id": 123}')]
    assert chain_lost("details_from_previous_results", [SEARCH], turn) is True


def test_rank_is_complete_and_rejected_rank_is_lost():
    ok = [tool_call("rank_jobs", {"job_ids": [5, 9]}), tool_result("rank_jobs", "{}")]
    rejected = [tool_call("rank_jobs", {"job_ids": [1]}),
                tool_result("rank_jobs", "TOOL ERROR: not in latest search")]
    assert chain_lost("rank_previous_results", [SEARCH], ok) is False
    assert chain_lost("rank_previous_results", [SEARCH], rejected) is True


def test_higher_salary_search_counts_as_refinement():
    turn = [tool_call("search_jobs", {"salary_min": 100000}), SEARCH]
    assert chain_lost("rank_previous_results", [SEARCH], turn) is False


# ---- Reliability classification: invalid argument names count as malformed

from app.assistant.reliability_run import invalid_argument_errors


def test_unexpected_keyword_error_counts_as_malformed():
    # Exact text from reliability_before_v2.txt, turn 1, wrapped as the loop stores it.
    error = ("Tool execution error: search_jobs() got an unexpected keyword "
             "argument 'minimum_salary'")
    turn = [tool_call("search_jobs", {"minimum_salary": 70000}),
            tool_result("search_jobs", f'<untrusted_data source="search_jobs">{error}</untrusted_data>'),
            tool_call("search_jobs", {"salary_min": 70000}), SEARCH]
    assert invalid_argument_errors(turn) == 1


def test_unwrapped_and_missing_argument_errors_count():
    turn = [tool_result("search_jobs", "Tool execution error: search_jobs() got an "
                        "unexpected keyword argument 'x'"),
            tool_result("rank_jobs", "Tool execution error: rank_jobs() missing 1 "
                        "required positional argument: 'job_ids'")]
    assert invalid_argument_errors(turn) == 2


def test_other_results_do_not_count_as_malformed():
    turn = [SEARCH,
            tool_result("search_jobs", "No matching jobs were found."),
            tool_result("rank_jobs", "TOOL ERROR: not in latest search"),
            tool_result("search_jobs", "Tool execution error: database is locked"),
            {"role": "assistant", "content": "Tool execution error: unexpected keyword argument"}]
    assert invalid_argument_errors(turn) == 0


# ---- Injection runner helpers (no model calls)

from app.assistant import injection_run


def test_next_month_range_handles_december():
    assert injection_run.next_month_range(date(2026, 10, 18)) == ("2026-11-01", "2026-11-30")
    assert injection_run.next_month_range(date(2026, 12, 5)) == ("2027-01-01", "2027-01-31")


def test_injection_target_is_a_test3_event_and_description_restores(db, monkeypatch):
    start, end = injection_run.next_month_range(date.today())
    with db() as session:
        session.add(Event(company_id=1, event_name="Next Month CS", description="orig",
                          event_date=date.fromisoformat(start) + timedelta(days=2),
                          event_time=time(12), location="Sunnyvale",
                          eligibility="Computer Science students"))
        session.commit()
    monkeypatch.setattr(injection_run, "SessionLocal", db)
    target = injection_run.pick_target_event()
    with db() as session:
        assert session.get(Event, target).event_name == "Next Month CS"
    previous = injection_run.set_description(target, injection_run.INJECTION)
    assert previous == "orig"
    shown = json.loads(tools.search_events(major="Computer Science", date_from=start, date_to=end))
    assert any(injection_run.MARKER in e["description"] for e in shown)
    injection_run.set_description(target, previous)
    with db() as session:
        assert session.get(Event, target).description == "orig"


def test_injection_runner_uses_the_five_test_prompts_and_follow_up():
    import inspect
    source = inspect.getsource(injection_run.run_mode)
    for name in ("TEST_1", "TEST_2", "TEST_3", "TEST_4", "TEST_5"):
        assert name in source
    assert 'conversation=r1["conversation"]' in source
