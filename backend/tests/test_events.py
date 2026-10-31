"""Lab 2 S4: the Kafka message envelope shared by every producer and consumer.

Run from backend/:  python -m pytest tests/test_events.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services.common import events


def test_topics_are_pair_prefixed_and_have_dead_letter_topics():
    assert events.TOPICS == [
        "p15.application.created", "p15.application.updated",
        "p15.application.status_changed", "p15.event.registration_created",
        "p15.job.created", "p15.memory.consolidate"]
    assert all(t.startswith("p15.") for t in events.ALL_TOPICS)
    assert events.dlq(events.JOB_CREATED) == "p15.job.created.dlq"
    assert len(events.ALL_TOPICS) == 12


def test_envelope_round_trip():
    event = events.make_event(events.APPLICATION_CREATED, "job:4:student:7",
                              {"job_id": 4, "student_id": 7}, trace_id="t-123")
    assert set(events.ENVELOPE_FIELDS) <= set(event) and event["version"] == 1
    assert event["trace_id"] == "t-123" and len(event["event_id"]) == 32
    assert event["created_at"].endswith("Z")
    assert events.decode(events.encode(event)) == event


def test_new_ids_are_unique_and_trace_defaults():
    a = events.make_event("x", "k", {})
    b = events.make_event("x", "k", {})
    assert a["event_id"] != b["event_id"] and a["trace_id"] != b["trace_id"]


@pytest.mark.parametrize("raw,reason", [
    (None, "empty"),
    (b"\xff\xfe not json", "not valid JSON"),
    (b"[1, 2]", "JSON object"),
    (json.dumps({"event_id": "x"}).encode(), "missing envelope fields"),
    (json.dumps({"event_id": "x", "trace_id": "t", "type": "a", "key": "k",
                 "payload": "oops", "created_at": "now"}).encode(), "payload"),
])
def test_poison_messages_are_detected(raw, reason):
    with pytest.raises(events.PoisonMessage, match=reason):
        events.decode(raw)


def test_dead_letter_record_keeps_original_and_reason():
    event = events.make_event(events.JOB_CREATED, "job:1", {"job_id": 1})
    record = events.dead_letter(event, events.JOB_CREATED, "boom", 3)
    assert record["original"] == event and record["attempts"] == 3
    raw = events.dead_letter(b"garbage", events.JOB_CREATED, "poison", 0)
    assert raw["original"] == {"raw": "garbage"}


def test_publisher_defaults_to_null_without_kafka(monkeypatch, capsys):
    monkeypatch.delenv("KAFKA_BOOTSTRAP", raising=False)
    events.set_publisher(None)
    pub = events.publisher()
    assert isinstance(pub, events.NullPublisher)
    pub.publish(events.JOB_CREATED, events.make_event(events.JOB_CREATED, "job:1", {}))
    assert "KAFKA_DISABLED" in capsys.readouterr().out
    events.set_publisher(None)
