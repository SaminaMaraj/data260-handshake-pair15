"""Lab 2 Part 6: token tracking, the 70% warning, compaction and recall.

A scripted model drives a real session (Pair 15 seed data) through the API:
several searches, then /compact. The tests check that token counts drop,
that the summary keeps the exact preferences, jobs, companies, events and
applications, and that a follow-up after compaction still works.
Run from backend/:  python -m pytest tests/test_compaction.py -q
"""
import html
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET_KEY", "compaction-test-key-not-for-production-012345")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")

import pytest
from fastapi.testclient import TestClient

from services.common import events


def call(name, args):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": args}}]}


class SessionModel:
    """Turn-by-turn script keyed on the user's latest message."""
    num_ctx = 8192

    def __init__(self):
        self.timeout, self.last_usage, self.prompt_tokens = 180, None, 1500

    def complete(self, messages, tools=None, response_format=None):
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        answered = messages[-1]["role"] == "tool"
        self.last_usage = {"prompt_tokens": self.prompt_tokens, "completion_tokens": 50,
                           "context_window": self.num_ctx, "estimated": False}
        if answered:
            return {"role": "assistant", "content": "Here is what I found."}
        if "internships in Sunnyvale" in last_user:
            return call("search_jobs", {"city": "Sunnyvale", "category": "internship"})
        if "events" in last_user:
            return call("search_events", {"city": "Palo Alto"})
        if "full-time in Cupertino" in last_user:
            return call("search_jobs", {"city": "Cupertino", "category": "full_time"})
        if "higher paying" in last_user:
            search = next(html.unescape(m["content"]) for m in reversed(messages)
                          if m.get("tool_name") == "search_jobs")
            ids = [int(i) for i in re.findall(r'"job_id"\s*:\s*(\d+)', search)]
            return call("rank_jobs", {"job_ids": ids, "limit": 3})
        return {"role": "assistant", "content": "OK."}


@pytest.fixture(scope="module")
def api():
    from services.common import mongo
    try:
        mongo.client().admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    name = f"p15_compaction_{uuid.uuid4().hex[:8]}"
    os.environ["MONGO_DB"] = name
    import contextlib
    import io
    from scripts.migrate_to_mongo import migrate, run_seed_into_sqlite
    with contextlib.redirect_stdout(io.StringIO()):
        assert migrate(run_seed_into_sqlite(), drop=True) == 0
    events.set_publisher(events.InMemoryPublisher())
    import services.assistant.agent.loop as loop
    model = SessionModel()
    original = loop.OllamaClient
    loop.OllamaClient = lambda: model
    from services.common.app_factory import build_service_app
    with TestClient(build_service_app("student")) as s, \
            TestClient(build_service_app("assistant")) as a:
        token = s.post("/users/login", json={"email": "p15.student.0001@example.com",
                                             "password": "Pair15SeedPassword!"}).json()["access_token"]
        yield a, {"Authorization": f"Bearer {token}"}, mongo.database(), model
    loop.OllamaClient = original
    events.set_publisher(None)
    mongo.client().drop_database(name)


def chat(api_, message, session_id=None):
    a, h, _, _ = api_
    body = {"message": message, **({"session_id": session_id} if session_id else {})}
    res = a.post("/assistant/chat", headers=h, json=body)
    assert res.status_code == 200, res.text
    return res.json()


def build_session(api_):
    first = chat(api_, "Find internships in Sunnyvale.")
    sid = first["session_id"]
    chat(api_, "Any events in Palo Alto?", sid)
    chat(api_, "Now full-time in Cupertino.", sid)
    return sid


def test_compaction_shrinks_and_keeps_the_facts(api):
    _, _, db, _ = api
    sid = build_session(api)
    before = db.conversations.find_one({"_id": sid})["messages"]
    result = chat(api, "/compact", sid)
    report = result["compaction"]
    assert result["command"] == "compact"
    assert report["tokens_after"] < report["tokens_before"]
    assert report["kept_last_search"] is True
    after = db.conversations.find_one({"_id": sid})["messages"]
    assert len(after) == 3 < len(before)
    summary = html.unescape(after[0]["content"])

    prefs = db.student_preferences.find_one({"_id": 1})
    assert prefs["preferred_city"] in summary                            # preferences
    from services.assistant import compaction
    seen = compaction.collect(before)
    for job in seen["jobs"].values():                                     # every job + company
        assert f"- {job['job_id']} | {job['title']} | {job['company']}" in summary
        assert str(job["salary"]) in summary and job["deadline"] in summary
    for ev in seen["events"].values():                                     # every event
        assert ev["event_name"] in summary
    app = db.applications.find_one({"student_id": 1})                     # applications
    job = db.jobs.find_one({"_id": app["job_id"]})
    assert f"{job['title']} at {job['company_name']} ({app['status']})" in summary
    assert "Current request: /compact" in summary
    assert '<untrusted_data source="session_summary">' in after[0]["content"]
    assert db.compactions.count_documents({"session_id": sid}) == 1


def test_follow_up_works_after_compaction(api):
    sid = build_session(api)
    chat(api, "/compact", sid)
    result = chat(api, "Make it higher paying.", sid)
    calls = [tc["function"] for m in result["conversation"] if m.get("role") == "assistant"
             for tc in m.get("tool_calls") or []]
    assert calls[-1]["name"] == "rank_jobs"
    assert not any(e["guardrail"] == "G2" for e in result["guardrails"])  # ids still valid
    assert result["status"] == "completed"


def test_token_counts_recorded_after_every_call(api):
    _, _, db, model = api
    model.prompt_tokens = 1500
    result = chat(api, "Find internships in Sunnyvale.")
    t = result["tokens"]
    assert t["model_calls"] == 2 and t["context_pct"] == pytest.approx(100 * 1550 / 8192, abs=0.1)
    assert t["warning"] is False
    assert db.token_usage.count_documents({"trace_id": result["trace_id"]}) == 2
    assert db.conversations.find_one({"_id": result["session_id"]})["tokens_total"] == 3100


def test_warning_above_70_and_auto_compaction_above_threshold(api):
    _, _, db, model = api
    model.prompt_tokens = 6000            # 6050 / 8192 = 73.9%: warn, no compaction
    warned = chat(api, "Find internships in Sunnyvale.")
    assert warned["tokens"]["warning"] is True and "compaction" not in warned
    model.prompt_tokens = 6500            # 79.9%: above the 75% threshold
    compacted = chat(api, "Find internships in Sunnyvale.", warned["session_id"])
    assert compacted["compaction"]["reason"] == "threshold"
    stored = db.conversations.find_one({"_id": warned["session_id"]})["messages"]
    assert stored[0]["content"].startswith("[Session summary")
    model.prompt_tokens = 1500
