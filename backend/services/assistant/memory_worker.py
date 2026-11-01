"""Memory consolidation consumer: Kafka topic p15.memory.consolidate.

Consolidation never runs inside a user request. /memory consolidate and
POST /assistant/session/end only PUBLISH a message; this worker does the
model calls and writes.

    python -m services.assistant.memory_worker        (KAFKA_BOOTSTRAP must be set)

Message actions (payload.action):
  consolidate  merge duplicates / resolve contradictions in student_memory
  extract      session ended: add lasting facts from the conversation to
               student_memory, then delete the conversation (layer 3)

Delivery guarantees
  * The offset is committed only AFTER the MongoDB writes succeed
    (enable.auto.commit=false, commit(message) after handle()).
  * Idempotent: event_id is recorded in processed_events; a redelivered
    message (worker crashed after writing, before committing) is skipped.
  * Crash-safe consolidation: new entries are tagged with the event_id, so a
    retry first removes a half-written attempt, then recomputes.
  * Bounded retries (MAX_ATTEMPTS, backoff) for transient failures such as
    the model being unreachable; then the message goes to
    p15.memory.consolidate.dlq and the consumer moves on (dead-lettered
    messages are recorded too, so a redelivery does not repeat them).
  * max.poll.interval.ms covers the worst case (all attempts timing out), and
    a failed commit is logged instead of crashing the worker.
  * A message that cannot be decoded (poison) goes to the DLQ at once.
"""
import os
import sys
import time

from datetime import datetime, timezone

from services.assistant import consolidation, memory
from services.common import events, tracing
from services.common.mongo import (
    CONVERSATIONS, PROCESSED_EVENTS, STUDENT_MEMORY, database, log_activity, utcnow)

GROUP_ID = "p15-memory-worker"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1, 3)          # waits between attempts 1->2 and 2->3

# Consolidation answers are long JSON documents (tens of entries), so the
# worker's model client gets its own budget: thinking off (qwen3 would
# otherwise spend minutes on hidden reasoning), a larger window for the
# input + output + one re-prompt, and a long per-call timeout.
MODEL_TIMEOUT_SECONDS = float(os.getenv("CONSOLIDATION_TIMEOUT_SECONDS", "600"))
MODEL_NUM_CTX = int(os.getenv("CONSOLIDATION_NUM_CTX", "16384"))
# A message may take MAX_ATTEMPTS model timeouts plus backoff. Kafka must not
# decide the worker is dead before that (default max.poll.interval.ms is
# 5 minutes, which caused a rebalance, a failed commit and a crash loop in
# the first real run).
MAX_POLL_INTERVAL_MS = int((MAX_ATTEMPTS * MODEL_TIMEOUT_SECONDS + sum(BACKOFF_SECONDS) + 120) * 1000)


def model_client():
    """The Ollama client used for consolidation and extraction."""
    from services.assistant.agent.client import OllamaClient
    return OllamaClient(timeout=MODEL_TIMEOUT_SECONDS, num_ctx=MODEL_NUM_CTX, think=False)
CONSOLIDATIONS = "memory_consolidations"
AUTO_CONSOLIDATE_ABOVE = 40       # extraction triggers consolidation past this


class PermanentError(Exception):
    """Retrying cannot help (bad payload): send to the DLQ immediately."""


# ---- business handlers (no Kafka here, so they are unit-testable) --------------------------

def run_consolidation(db, student_id: int, event_id: str, client, trace_id=None) -> dict:
    record = db[CONSOLIDATIONS].find_one({"_id": event_id})
    if record and record.get("status") == "applied":
        return {"status": "already_applied", "after": record["after_count"]}

    # Remove a half-written earlier attempt of this same event (crash-safety).
    db[STUDENT_MEMORY].delete_many({"student_id": student_id, "consolidation_id": event_id})

    stored = memory.list_entries(db, student_id)
    if len(stored) < 2:
        return {"status": "nothing_to_do", "before": len(stored)}
    local = [{"id": n, "date": e["date"], "category": e["category"],
              "description": e["description"]} for n, e in enumerate(stored, start=1)]
    started = time.monotonic()
    result = consolidation.consolidate(local, client)
    elapsed_ms = round((time.monotonic() - started) * 1000)

    now = utcnow()
    new_docs = [{"student_id": student_id, "date": e["date"], "category": e["category"],
                 "description": e["description"], "source": "consolidated",
                 "consolidation_id": event_id, "merged_from": len(e["sources"]),
                 "created_at": now} for e in result["entries"]]
    if new_docs:
        db[STUDENT_MEMORY].insert_many(new_docs)
    db[STUDENT_MEMORY].delete_many({"_id": {"$in": [e["_id"] for e in stored]}})

    db[CONSOLIDATIONS].replace_one({"_id": event_id}, {
        "_id": event_id, "student_id": student_id, "trace_id": trace_id,
        "status": "applied", "method": result["method"],
        "model_attempts": result["model_attempts"],
        "model_calls": result.get("model_calls"),
        "fallback_categories": result.get("fallback_categories", []),
        "before_count": len(stored), "after_count": len(new_docs),
        "before": [memory.render_line(e) for e in stored],
        "after": [memory.render_line(e) for e in new_docs],
        "decisions": result["decisions"], "corrections": result["corrections"],
        "model_errors": result["errors"], "elapsed_ms": elapsed_ms, "at": now,
    }, upsert=True)
    log_activity(db, student_id, "memory_consolidated", before=len(stored),
                 after=len(new_docs), method=result["method"], trace_id=trace_id)
    return {"status": "applied", "before": len(stored), "after": len(new_docs),
            "method": result["method"], "elapsed_ms": elapsed_ms}


def run_extraction(db, student_id: int, session_id: str, client, trace_id=None) -> dict:
    session = db[CONVERSATIONS].find_one({"_id": session_id, "student_id": student_id})
    if session is None:
        return {"status": "session_gone"}  # already processed
    facts = consolidation.extract(session.get("messages", []), client)
    for fact in facts:
        memory.add_entry(db, student_id, fact["category"], fact["description"],
                         source="session")
    db[CONVERSATIONS].delete_one({"_id": session_id})  # layer 3 is discarded
    log_activity(db, student_id, "memory_extracted", facts=len(facts),
                 session_id=session_id, trace_id=trace_id)
    total = db[STUDENT_MEMORY].count_documents({"student_id": student_id})
    if total > AUTO_CONSOLIDATE_ABOVE:
        follow = events.make_event(events.MEMORY_CONSOLIDATE, f"student:{student_id}",
                                   {"action": "consolidate", "student_id": student_id},
                                   trace_id=trace_id)
        events.publisher().publish(events.MEMORY_CONSOLIDATE, follow)
    return {"status": "extracted", "facts": len(facts), "total": total}


def handle(db, event: dict, client) -> dict:
    """Process one decoded envelope exactly once."""
    if db[PROCESSED_EVENTS].find_one({"_id": event["event_id"]}, {"_id": 1}):
        return {"status": "duplicate_skipped"}
    payload = event["payload"]
    student_id = payload.get("student_id")
    if not isinstance(student_id, int):
        raise PermanentError("payload.student_id must be an integer")
    action = payload.get("action")
    if action == "consolidate":
        outcome = run_consolidation(db, student_id, event["event_id"], client,
                                    event.get("trace_id"))
    elif action == "extract":
        if not isinstance(payload.get("session_id"), str):
            raise PermanentError("payload.session_id is required for extract")
        outcome = run_extraction(db, student_id, payload["session_id"], client,
                                 event.get("trace_id"))
    else:
        raise PermanentError(f"unknown action {action!r}")
    # Recorded last: if we crash before this line the message is redelivered
    # and the handlers above are safe to run again.
    db[PROCESSED_EVENTS].insert_one({"_id": event["event_id"], "type": event["type"],
                                     "trace_id": event.get("trace_id"),
                                     "processed_at": utcnow()})
    return outcome


def process_message(db, raw: bytes, client, dead_letter, sleep=time.sleep) -> dict:
    """decode -> handle with bounded retries -> DLQ on failure.

    Returns the outcome; the caller commits the Kafka offset afterwards in
    every case (success, duplicate, or dead-lettered), so the consumer
    never gets stuck on one message.
    """
    try:
        event = events.decode(raw)
    except events.PoisonMessage as exc:
        dead_letter(events.dead_letter(raw, events.MEMORY_CONSOLIDATE, str(exc), 0))
        tracing.log("kafka_message", status="dead_lettered", reason=f"poison: {exc}")
        return {"status": "dead_lettered", "reason": f"poison: {exc}", "attempts": 0}

    # Continue the trace of the request that published this message.
    trace, token = tracing.start("p15-memory-worker", event["payload"].get("action", "?"),
                                 event.get("trace_id"))
    try:
        trace.spans.append({"stage": "queue", "name": events.MEMORY_CONSOLIDATE,
                            "ms": kafka_wait_ms(event), "at_ms": 0.0})
        outcome = _process(db, event, client, dead_letter, sleep)
        tracing.log("kafka_message", topic=events.MEMORY_CONSOLIDATE,
                    event_id=event["event_id"], status=outcome["status"],
                    attempts=outcome.get("attempts"), kafka_wait_ms=trace.spans[0]["ms"],
                    ms=trace.elapsed_ms(), db_ms=round(trace.db_ms, 1))
        tracing.save(db, trace, status=outcome["status"], error=outcome.get("reason"))
        return outcome
    finally:
        tracing.finish(token)


def kafka_wait_ms(event: dict) -> float:
    """Time the message waited in Kafka: published (created_at) -> picked up."""
    try:
        created = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        return round(max(0.0, (datetime.now(timezone.utc) - created).total_seconds() * 1000), 1)
    except (KeyError, ValueError, AttributeError):
        return 0.0


def _process(db, event: dict, client, dead_letter, sleep) -> dict:
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            outcome = handle(db, event, client)
            return {**outcome, "attempts": attempt, "event_id": event["event_id"],
                    "trace_id": event["trace_id"]}
        except PermanentError as exc:
            last_error, attempt_used = f"permanent: {exc}", attempt
            break
        except Exception as exc:  # transient: model down, Mongo blip, ...
            last_error, attempt_used = f"{type(exc).__name__}: {exc}", attempt
            print(f"MEMORY_WORKER retry event={event['event_id'][:8]} "
                  f"attempt={attempt}/{MAX_ATTEMPTS} error={last_error}")
            if attempt < MAX_ATTEMPTS:
                sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
    dead_letter(events.dead_letter(event, events.MEMORY_CONSOLIDATE, last_error, attempt_used))
    # Recorded so a redelivery (e.g. after a crash before the commit) is
    # skipped instead of being retried and dead-lettered a second time.
    db[PROCESSED_EVENTS].update_one(
        {"_id": event["event_id"]},
        {"$setOnInsert": {"type": event["type"], "trace_id": event.get("trace_id"),
                          "status": "dead_lettered", "processed_at": utcnow()}},
        upsert=True)
    return {"status": "dead_lettered", "reason": last_error, "attempts": attempt_used,
            "event_id": event["event_id"], "trace_id": event["trace_id"]}


# ---- the Kafka loop ---------------------------------------------------------------------------

def consume(consumer, message, db, client, dead_letter) -> dict:
    """Process one Kafka message, then commit its offset.

    A failed commit (for example after a consumer-group rebalance) is logged,
    not raised: the message will simply be delivered again, and
    processed_events makes that redelivery a no-op.
    """
    from confluent_kafka import KafkaException

    started = time.monotonic()
    outcome = process_message(db, message.value(), client, dead_letter)
    try:
        consumer.commit(message=message, asynchronous=False)  # after the DB write
        committed = True
    except KafkaException as exc:
        committed = False
        print(f"MEMORY_WORKER commit failed ({exc}); the message will be redelivered "
              "and skipped as already processed")
    print(f"MEMORY_WORKER partition={message.partition()} offset={message.offset()} "
          f"trace_id={outcome.get('trace_id', '-')} status={outcome['status']} "
          f"attempts={outcome.get('attempts')} committed={committed} "
          f"ms={round((time.monotonic() - started) * 1000)} "
          f"detail={ {k: v for k, v in outcome.items() if k in ('before', 'after', 'method', 'facts', 'reason')} }",
          flush=True)
    return {**outcome, "committed": committed}


def main() -> None:  # pragma: no cover - needs a broker; verified in Docker/EKS
    from confluent_kafka import Consumer

    bootstrap = os.getenv("KAFKA_BOOTSTRAP")
    if not bootstrap:
        sys.exit("KAFKA_BOOTSTRAP is not set")
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": GROUP_ID,
                         "enable.auto.commit": False, "auto.offset.reset": "earliest",
                         "max.poll.interval.ms": MAX_POLL_INTERVAL_MS})
    consumer.subscribe([events.MEMORY_CONSOLIDATE])
    db, client, dlq_topic = database(), model_client(), events.dlq(events.MEMORY_CONSOLIDATE)
    memory.seed_rules(db)

    def dead_letter(record):
        events.publisher().publish(dlq_topic, {
            "event_id": events.new_id(),
            "trace_id": (record["original"] or {}).get("trace_id") or events.new_id(),
            "type": "dead_letter", "key": "dlq", "payload": record,
            "created_at": record["failed_at"]})
        events.publisher().flush()

    print(f"MEMORY_WORKER listening on {events.MEMORY_CONSOLIDATE} as {GROUP_ID} "
          f"(model timeout {MODEL_TIMEOUT_SECONDS:.0f}s, num_ctx {MODEL_NUM_CTX}, think off, "
          f"max.poll.interval {MAX_POLL_INTERVAL_MS // 1000}s)", flush=True)
    try:
        while True:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                print(f"MEMORY_WORKER kafka error: {message.error()}", flush=True)
                continue
            consume(consumer, message, db, client, dead_letter)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
