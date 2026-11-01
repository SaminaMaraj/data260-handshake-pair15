"""Lab 2 Part 6: trace_id propagation, stage timing and token tracking.

Run from backend/:  python -m pytest tests/test_tracing.py -q
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET_KEY", "tracing-test-key-not-for-production-0123456789")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")

import pytest
from fastapi.testclient import TestClient

from services.common import events, tracing


class TimedModel:
    """Takes 50 ms but reports 30 ms of inference (so ~20 ms queue wait)."""
    num_ctx = 8192

    def __init__(self, script):
        self.script, self.calls, self.timeout, self.last_usage = script, 0, 180, None

    def complete(self, messages, tools=None, response_format=None):
        started = time.perf_counter()
        time.sleep(0.05)
        reply = self.script(messages, self.calls)
        self.calls += 1
        wall = (time.perf_counter() - started) * 1000
        self.last_usage = {"prompt_tokens": 1200 + 400 * self.calls, "completion_tokens": 60,
                           "context_window": self.num_ctx, "estimated": False,
                           "wall_ms": wall, "inference_ms": 30.0, "queue_wait_ms": wall - 30.0}
        return reply


def search_then_answer(messages, step):
    if step == 0:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "search_jobs", "arguments": {"city": "Sunnyvale"}}}]}
    return {"role": "assistant", "content": "I found some jobs in Sunnyvale."}


@pytest.fixture()
def stack(monkeypatch):
    from services.common import mongo
    try:
        mongo.client().admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    name = f"p15_tracing_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("MONGO_DB", name)
    bus = events.InMemoryPublisher()
    events.set_publisher(bus)
    from services.common.app_factory import build_service_app
    import services.assistant.agent.loop as loop
    model = TimedModel(search_then_answer)
    monkeypatch.setattr(loop, "OllamaClient", lambda: model)
    with TestClient(build_service_app("student")) as s, \
            TestClient(build_service_app("assistant")) as a:
        s.post("/users/register", json={"email": "t@p15.dev", "password": "StrongPass1!",
                                        "role": "student"})
        token = s.post("/users/login", json={"email": "t@p15.dev", "password": "StrongPass1!"}
                       ).json()["access_token"]
        yield a, {"Authorization": f"Bearer {token}"}, mongo.database(), bus, model
    events.set_publisher(None)
    mongo.client().drop_database(name)


def test_trace_id_generated_and_returned(stack):
    a, h, db, _, _ = stack
    res = a.post("/assistant/chat", headers=h, json={"message": "Find jobs in Sunnyvale"})
    body = res.json()
    trace_id = res.headers["X-Trace-Id"]
    assert len(trace_id) == 32 and body["trace_id"] == trace_id
    doc = db.traces.find_one({"trace_id": trace_id})
    assert doc["service"] == "p15-assistant" and doc["status"] == "completed"
    s = doc["stages"]
    assert set(s) == {"queue_wait_ms", "model_ms", "db_ms", "tool_ms", "other_ms", "total_ms"}
    assert s["model_ms"] == pytest.approx(60.0)                  # 2 calls x 30 ms reported
    assert s["queue_wait_ms"] >= 30                              # ~2 x 20 ms waiting
    assert s["db_ms"] > 0 and doc["db_ops"] > 0                  # auth, memory, search...
    parts = s["queue_wait_ms"] + s["model_ms"] + s["db_ms"] + s["tool_ms"] + s["other_ms"]
    assert parts == pytest.approx(s["total_ms"], abs=1.0)        # stages add up
    assert [sp["stage"] for sp in doc["spans"]] == ["model", "tool", "model"]


def test_caller_trace_id_is_continued_and_bad_ids_ignored(stack):
    a, h, db, _, _ = stack
    res = a.post("/assistant/chat", headers={**h, "X-Trace-Id": "jmeter-run-0001"},
                 json={"message": "Find jobs"})
    assert res.headers["X-Trace-Id"] == "jmeter-run-0001"
    res = a.post("/assistant/chat", headers={**h, "X-Trace-Id": "bad id\n{inject}"},
                 json={"message": "Find jobs"})
    assert res.headers["X-Trace-Id"] != "bad id\n{inject}" and len(res.headers["X-Trace-Id"]) == 32


def test_trace_id_propagates_through_kafka_to_the_worker(stack, monkeypatch):
    a, h, db, bus, _ = stack
    res = a.post("/assistant/chat", headers=h, json={"message": "/memory consolidate"})
    trace_id = res.headers["X-Trace-Id"]
    message = bus.messages[events.MEMORY_CONSOLIDATE][-1]
    assert message["trace_id"] == trace_id                       # HTTP -> Kafka
    from services.assistant import memory, memory_worker
    for i in range(3):
        memory.add_entry(db, 1, "skill", f"Knows tool {i}")
    class Echo:
        def complete(self, messages, tools=None, response_format=None):
            rows = [int(n) for n in __import__("re").findall(r"\[(\d+)\]", messages[-1]["content"])]
            return {"role": "assistant", "content": json.dumps({"groups": [
                {"ids": rows, "type": "duplicate", "reason": "same"}]})}
    outcome = memory_worker.process_message(db, events.encode(message), Echo(), [].append,
                                            sleep=lambda _: None)
    assert outcome["status"] == "applied"
    worker = db.traces.find_one({"trace_id": trace_id, "service": "p15-memory-worker"})
    assert worker is not None                                    # Kafka -> worker
    assert worker["spans"][0]["stage"] == "queue"                # Kafka wait recorded
    assert any(sp["stage"] == "model" for sp in worker["spans"])
    assert db.activity_logs.find_one({"action": "memory_consolidated", "trace_id": trace_id})


def test_failed_trace_is_recorded(stack, monkeypatch):
    a, h, db, _, model = stack
    model.script = lambda m, s: {"role": "assistant", "content": "Ollama request failed: refused"}
    res = a.post("/assistant/chat", headers=h, json={"message": "Find jobs"})
    doc = db.traces.find_one({"trace_id": res.headers["X-Trace-Id"]})
    assert res.json()["status"] == "model_error"
    assert doc["status"] == "model_error" and "refused" in doc["error"]


def test_token_tracking_in_response(stack):
    a, h, db, _, _ = stack
    tokens = a.post("/assistant/chat", headers=h, json={"message": "Find jobs"}).json()["tokens"]
    assert tokens["model_calls"] == 2 and tokens["estimated"] is False
    assert tokens["prompt_tokens"] == 1600 + 2000 and tokens["completion_tokens"] == 120
    assert tokens["context_used"] == 2060 and tokens["context_window"] == 8192
    assert tokens["context_pct"] == pytest.approx(25.1) and tokens["warning"] is False
    assert [c["call"] for c in tokens["calls"]] == [1, 2]


def test_every_service_logs_json_with_trace_id(stack, capsys):
    a, h, _, _, _ = stack
    res = a.post("/assistant/chat", headers=h, json={"message": "Find jobs"})
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith("{")]
    mine = [l for l in lines if l.get("trace_id") == res.headers["X-Trace-Id"]]
    kinds = {l["event"] for l in mine}
    assert {"request", "model_call"} <= kinds
    request = next(l for l in mine if l["event"] == "request")
    assert request["service"] == "p15-assistant" and request["status"] == 200
