"""Memory consolidation evidence run (Lab 2 Part 3) with the real model.

  1. Seeds one student's learned memory with the 62-entry fixture
     (services/assistant/memory_seed.py: 27 facts, 4 exact-duplicate groups,
     5 contradictions)
  2. Triggers consolidation
       --via-kafka  publish to p15.memory.consolidate and wait for the
                    memory worker (python -m services.assistant.memory_worker)
                    to finish: the path the handout requires
       --direct     run the same handler in this process (no Kafka; for a
                    quick check before the cluster is up)
  3. Prints BEFORE, AFTER, every decision, the model's corrected mistakes,
     and the automatic checks (< 40 entries, duplicates merged,
     contradictions resolved)

From backend/, with MONGO_URL, OLLAMA_BASE_URL and (for --via-kafka)
KAFKA_BOOTSTRAP set:
    python scripts/memory_consolidation_report.py --student 1 --via-kafka \
        | tee ../docs/evidence/memory_consolidation.txt
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.assistant import memory, memory_seed, memory_worker
from services.common import events
from services.common.mongo import database, ensure_indexes


def show(title, lines):
    print(f"\n===== {title} ({len(lines)}) =====")
    for n, line in enumerate(lines, start=1):
        print(f"{n:3}. {line}")


def main():
    # Print as we go even when piped into tee (Python buffers pipes otherwise).
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--student", type=int, default=1)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--via-kafka", action="store_true")
    mode.add_argument("--direct", action="store_true")
    parser.add_argument("--timeout", type=int,
                        default=int(memory_worker.MAX_POLL_INTERVAL_MS / 1000),
                        help="seconds to wait for the worker (default: its worst case)")
    args = parser.parse_args()

    db = database()
    ensure_indexes(db)
    count = memory_seed.seed(db, args.student)
    before = [memory.render_line(e) for e in memory.list_entries(db, args.student)]
    print(f"Seeded {count} memory entries for student {args.student}: "
          f"{memory_seed.DISTINCT_FACTS} facts, {len(memory_seed.EXACT_DUPLICATE_GROUPS)} "
          f"exact-duplicate groups, {len(memory_seed.CONTRADICTIONS)} contradictions")
    show("BEFORE", before)

    event = events.make_event(events.MEMORY_CONSOLIDATE, f"student:{args.student}",
                              {"action": "consolidate", "student_id": args.student})
    started = time.monotonic()
    if args.via_kafka:
        events.publisher().publish(events.MEMORY_CONSOLIDATE, event)
        events.publisher().flush()
        print(f"\nPublished to {events.MEMORY_CONSOLIDATE}: event_id={event['event_id']} "
              f"trace_id={event['trace_id']}; waiting for the memory worker...")
        record, last_note = None, 0.0
        while time.monotonic() - started < args.timeout:
            record = db[memory_worker.CONSOLIDATIONS].find_one({"_id": event["event_id"]})
            if record and record.get("status") == "applied":
                break
            done = db.processed_events.find_one({"_id": event["event_id"]})
            if done and done.get("status") == "dead_lettered":
                sys.exit("The worker dead-lettered this message after its retries: "
                         "see `docker compose logs p15-memory-worker`.")
            if time.monotonic() - last_note >= 30:
                last_note = time.monotonic()
                print(f"  ...still waiting ({time.monotonic() - started:.0f}s)")
            time.sleep(2)
        if not record:
            sys.exit("No result in time: check `docker compose logs p15-memory-worker`.")
    else:
        outcome = memory_worker.process_message(db, events.encode(event), memory_worker.model_client(),
                                                lambda r: print("DEAD-LETTERED:", r))
        print(f"\nDirect run outcome: {outcome}")
        record = db[memory_worker.CONSOLIDATIONS].find_one({"_id": event["event_id"]})
        if not record:
            sys.exit("Consolidation did not complete (see the outcome above).")

    after = [memory.render_line(e) for e in memory.list_entries(db, args.student)]
    show("AFTER", after)

    print(f"\n===== HOW IT WAS DONE =====")
    print(f"method={record['method']}  model_attempts={record['model_attempts']}  "
          f"model_time_ms={record['elapsed_ms']}  end_to_end_s={time.monotonic() - started:.1f}")
    print("\n===== DECISIONS =====")
    for d in record["decisions"]:
        print(f"- [{d['step']}] {d['action']} sources={d['sources']}\n"
              f"    kept: {d.get('kept', '-')}\n    reason: {d.get('reason', '')}")
    print("\n===== MODEL ANSWERS REJECTED BY VALIDATION (then re-prompted) =====")
    for e in record["model_errors"] or []:
        print(f"- attempt {e['attempt']}:")
        for err in e["errors"]:
            print(f"    {err}")
    if not record["model_errors"]:
        print("(none: the first answer passed validation)")
    print("\n===== MODEL VALUES CORRECTED BY CODE IN THE ACCEPTED ANSWER =====")
    for c in record["corrections"] or ["(none)"]:
        print(f"- {c}")

    print("\n===== CHECKS =====")
    results = memory_seed.check(after)
    for name, passed, detail in results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    passed = sum(r[1] for r in results)
    print(f"\nRESULT: {passed}/{len(results)} checks passed; "
          f"{record['before_count']} -> {record['after_count']} entries")


if __name__ == "__main__":
    main()
