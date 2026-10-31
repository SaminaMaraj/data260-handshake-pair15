"""Kafka message envelope, topic names and publishers for Pair 15 (Lab 2 S4).

Every message on every topic has the same envelope:

    {
      "event_id":   "9f1c...",        unique per message; consumers de-duplicate on it
      "trace_id":   "4b7e...",        the assistant/API request that caused it (tracing)
      "type":       "application.created",
      "key":        "job:42:student:7", also the Kafka message key (ordering per entity)
      "payload":    {...},            the business data
      "created_at": "2026-10-30T18:30:00.123Z",
      "version":    1
    }

Topics are prefixed with p15. as the handout requires. Each has a dead-letter
topic "<topic>.dlq" for messages that still fail after bounded retries.

Publishers:
  KafkaPublisher     real broker (confluent-kafka), idempotent, acks=all
  NullPublisher      KAFKA_BOOTSTRAP not set: logs instead of sending, so a
                     service still runs without Kafka (local dev, tests)
  InMemoryPublisher  tests: keeps messages in a list per topic

Consumers decode with decode(); a message that is not valid JSON or lacks
the envelope fields raises PoisonMessage and should go straight to the DLQ.
"""
import json
import os
import uuid
from datetime import datetime, timezone

PREFIX = "p15."

APPLICATION_CREATED = PREFIX + "application.created"
APPLICATION_UPDATED = PREFIX + "application.updated"
APPLICATION_STATUS_CHANGED = PREFIX + "application.status_changed"
EVENT_REGISTRATION_CREATED = PREFIX + "event.registration_created"
JOB_CREATED = PREFIX + "job.created"
MEMORY_CONSOLIDATE = PREFIX + "memory.consolidate"   # Samina: assistant memory

TOPICS = [APPLICATION_CREATED, APPLICATION_UPDATED, APPLICATION_STATUS_CHANGED,
          EVENT_REGISTRATION_CREATED, JOB_CREATED, MEMORY_CONSOLIDATE]
ENVELOPE_FIELDS = ("event_id", "trace_id", "type", "key", "payload", "created_at")
VERSION = 1


def dlq(topic: str) -> str:
    return topic + ".dlq"


ALL_TOPICS = TOPICS + [dlq(t) for t in TOPICS]


class PoisonMessage(ValueError):
    """The message cannot be processed no matter how often it is retried."""


def new_id() -> str:
    return uuid.uuid4().hex


def make_event(event_type: str, key: str, payload: dict, *, trace_id: str | None = None,
               event_id: str | None = None) -> dict:
    return {
        "event_id": event_id or new_id(),
        "trace_id": trace_id or new_id(),
        "type": event_type,
        "key": str(key),
        "payload": payload,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                      .replace("+00:00", "Z"),
        "version": VERSION,
    }


def encode(event: dict) -> bytes:
    return json.dumps(event, default=str, separators=(",", ":")).encode("utf-8")


def decode(raw: bytes | str | None) -> dict:
    """Bytes from Kafka -> envelope dict, or PoisonMessage."""
    if raw is None:
        raise PoisonMessage("empty message")
    try:
        event = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PoisonMessage(f"not valid JSON: {exc}") from exc
    if not isinstance(event, dict):
        raise PoisonMessage("envelope must be a JSON object")
    missing = [f for f in ENVELOPE_FIELDS if f not in event]
    if missing:
        raise PoisonMessage(f"missing envelope fields: {missing}")
    if not isinstance(event["payload"], dict):
        raise PoisonMessage("payload must be a JSON object")
    return event


def dead_letter(event_or_raw, topic: str, error: str, attempts: int) -> dict:
    """The DLQ record: the original message plus why and when it failed."""
    original = event_or_raw if isinstance(event_or_raw, dict) else {
        "raw": event_or_raw.decode("utf-8", "replace") if isinstance(event_or_raw, bytes)
        else str(event_or_raw)}
    return {"original": original, "source_topic": topic, "error": error,
            "attempts": attempts,
            "failed_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}


# ---- publishers --------------------------------------------------------------------

class NullPublisher:
    """Used when KAFKA_BOOTSTRAP is unset: the request still succeeds."""

    def publish(self, topic: str, event: dict) -> None:
        print(f"KAFKA_DISABLED would publish {topic} event_id={event['event_id']} "
              f"trace_id={event['trace_id']}")

    def flush(self, timeout: float = 5.0) -> None:
        pass


class InMemoryPublisher:
    def __init__(self):
        self.messages: dict[str, list[dict]] = {}

    def publish(self, topic: str, event: dict) -> None:
        self.messages.setdefault(topic, []).append(event)

    def flush(self, timeout: float = 5.0) -> None:
        pass


class KafkaPublisher:
    def __init__(self, bootstrap: str):
        from confluent_kafka import Producer
        self._producer = Producer({
            "bootstrap.servers": bootstrap,
            "client.id": os.getenv("SERVICE_NAME", "p15-service"),
            # Broker de-duplicates producer retries; never acknowledged
            # until every in-sync replica has the message.
            "enable.idempotence": True,
            "acks": "all",
            "linger.ms": 5,
        })

    def publish(self, topic: str, event: dict) -> None:
        self._producer.produce(topic, key=event["key"].encode(), value=encode(event),
                               headers={"trace_id": event["trace_id"],
                                        "event_type": event["type"]})
        self._producer.poll(0)  # serve delivery callbacks

    def flush(self, timeout: float = 5.0) -> None:
        self._producer.flush(timeout)


_publisher = None


def publisher():
    """Process-wide publisher chosen from KAFKA_BOOTSTRAP."""
    global _publisher
    if _publisher is None:
        bootstrap = os.getenv("KAFKA_BOOTSTRAP", "").strip()
        _publisher = KafkaPublisher(bootstrap) if bootstrap else NullPublisher()
    return _publisher


def set_publisher(p) -> None:
    """Tests (and the harness) swap in an InMemoryPublisher."""
    global _publisher
    _publisher = p
