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
    p15.memory.consolidate.dlq and the consumer moves on.
  * A message that cannot be decoded (poison) goes to the DLQ at once.
"""
import os
import sys
import time

from services.assistant import consolidation, memory
from services.common import events
from services.common.mongo import (
    CONVERSATIONS, PROCESSED_EVENTS, STUDENT_MEMORY, database, log_activity, utcnow)

GROUP_ID = "p15-memory-worker"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1, 3)          # waits between attempts 1->2 and 2->3
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
        return {"status": "dead_lettered", "reason": f"poison: {exc}", "attempts": 0}

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
    return {"status": "dead_lettered", "reason": last_error, "attempts": attempt_used,
            "event_id": event["event_id"], "trace_id": event["trace_id"]}


# ---- the Kafka loop ---------------------------------------------------------------------------

def main() -> None:  # pragma: no cover - needs a broker; verified in Docker/EKS
    from confluent_kafka import Consumer

    from services.assistant.agent.client import OllamaClient

    bootstrap = os.getenv("KAFKA_BOOTSTRAP")
    if not bootstrap:
        sys.exit("KAFKA_BOOTSTRAP is not set")
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": GROUP_ID,
                         "enable.auto.commit": False, "auto.offset.reset": "earliest"})
    consumer.subscribe([events.MEMORY_CONSOLIDATE])
    db, client, dlq_topic = database(), OllamaClient(), events.dlq(events.MEMORY_CONSOLIDATE)
    memory.seed_rules(db)

    def dead_letter(record):
        events.publisher().publish(dlq_topic, {
            "event_id": events.new_id(),
            "trace_id": (record["original"] or {}).get("trace_id") or events.new_id(),
            "type": "dead_letter", "key": "dlq", "payload": record,
            "created_at": record["failed_at"]})
        events.publisher().flush()

    print(f"MEMORY_WORKER listening on {events.MEMORY_CONSOLIDATE} as {GROUP_ID}")
    try:
        while True:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                print(f"MEMORY_WORKER kafka error: {message.error()}")
                continue
            started = time.monotonic()
            outcome = process_message(db, message.value(), client, dead_letter)
            consumer.commit(message=message, asynchronous=False)  # after the DB write
            print(f"MEMORY_WORKER partition={message.partition()} offset={message.offset()} "
                  f"trace_id={outcome.get('trace_id', '-')} status={outcome['status']} "
                  f"attempts={outcome.get('attempts')} "
                  f"ms={round((time.monotonic() - started) * 1000)} "
                  f"detail={ {k: v for k, v in outcome.items() if k in ('before', 'after', 'method', 'facts', 'reason')} }")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
