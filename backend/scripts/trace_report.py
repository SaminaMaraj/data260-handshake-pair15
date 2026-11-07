"""Trace load and latency analysis (Lab 2 Part 6).

  load    send N assistant requests through the gateway as a real student;
          each request gets its own trace (X-Trace-Id)
  report  read the stored traces and print, per stage, mean / p50 / p95 and
          share of total latency, which stage dominates, and the full
          timeline of one successful and one failed trace
  show    print one trace by id

From backend/ (the stack running, real Ollama behind the assistant):

    python scripts/trace_report.py load --base http://localhost:9150 \
        --email p15.student.0001@example.com --password 'Pair15SeedPassword!' --n 50
    python scripts/trace_report.py report --last 50 | tee ../docs/evidence/trace_report.txt

Stages: queue_wait (waiting for the model), model (inference reported by
Ollama), db (MongoDB commands), tool (tool code excluding its DB time),
other (validation, guardrails, serialization).
"""
import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STAGES = ["queue_wait_ms", "model_ms", "db_ms", "tool_ms", "other_ms"]
PROMPTS = [
    "Find an internship in my city.",
    "Find a remote data science internship.",
    "Find an event for computer science students next month.",
    "Find full-time jobs in Cupertino.",
    "Show part-time jobs in Palo Alto.",
    "Find a job at Nonexistent Labs.",
    "Find internships that pay at least 100000.",
    "What resume review events are coming up?",
    "Find analyst jobs with SQL skills.",
    "Find on-campus jobs.",
]


def _post(url, body, headers=None, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read()), dict(res.headers), started
    except urllib.error.HTTPError as err:
        return err.code, {"detail": err.read().decode()[:200]}, dict(err.headers), started


def load(args):
    headers = {}

    def login():
        status, body, _, _ = _post(f"{args.base}/users/login",
                                   {"email": args.email, "password": args.password})
        if status != 200:
            sys.exit(f"login failed ({status}): {body}")
        headers["Authorization"] = f"Bearer {body['access_token']}"

    login()

    def one(i):
        prompt = PROMPTS[i % len(PROMPTS)]
        code, result, res_headers, started = _post(f"{args.base}/assistant/chat",
                                                   {"message": prompt}, headers)
        if code == 401:
            # Sessions expire after SESSION_TTL_MINUTES (30): log in again and retry.
            print(f"     session expired at request {i + 1}: logging in again", flush=True)
            login()
            code, result, res_headers, started = _post(f"{args.base}/assistant/chat",
                                                       {"message": prompt}, dict(headers))
        ms = (time.perf_counter() - started) * 1000
        line = (f"{i + 1:3}. {code} {result.get('status', '-'):22} {ms:8.0f} ms  "
                f"trace={res_headers.get('X-Trace-Id', res_headers.get('x-trace-id', '-'))}  {prompt}")
        print(line, flush=True)
        return code

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        codes = list(pool.map(one, range(args.n)))
    print(f"\n{args.n} requests, concurrency {args.concurrency}, "
          f"{sum(c == 200 for c in codes)} HTTP 200, {time.perf_counter() - started:.1f} s")


def pct(values, q):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q / 100 * (len(values) - 1))))]


def timeline(doc):
    print(f"trace_id {doc['trace_id']}  service {doc['service']}  {doc['name']}")
    print(f"status {doc['status']}  http {doc.get('http_status')}  db_ops {doc['db_ops']}"
          + (f"\nerror  {doc['error']}" if doc.get("error") else ""))
    for span in doc["spans"]:
        detail = ""
        if span["stage"] == "model":
            detail = (f"  inference {span.get('inference_ms')} ms, wait "
                      f"{round(span['ms'] - (span.get('inference_ms') or span['ms']), 1)} ms, "
                      f"tokens {span.get('prompt_tokens')}+{span.get('completion_tokens')}")
        elif span["stage"] == "tool":
            detail = f"  (db {span.get('db_ms', 0)} ms)"
        print(f"  @{span.get('at_ms', 0):9.1f} ms  {span['stage']:6} {span['name']:24} "
              f"{span['ms']:9.1f} ms{detail}")
    print("  stages: " + ", ".join(f"{k.replace('_ms', '')} {v} ms" for k, v in doc["stages"].items()))


def report(args):
    from services.common.mongo import database
    db = database()
    # Requests rejected before reaching the assistant (expired or missing login)
    # say nothing about assistant latency, so they are counted but not analyzed.
    query = {"service": "p15-assistant", "name": "POST /assistant/chat"}
    rejected = db.traces.count_documents({**query, "http_status": {"$in": [401, 403]}})
    docs = list(db.traces.find({**query, "http_status": {"$nin": [401, 403]}})
                .sort("at", -1).limit(args.last))
    if rejected:
        print(f"(excluded {rejected} requests rejected by authentication, HTTP 401/403)")
    if not docs:
        sys.exit("No assistant traces stored yet: run the load command first.")
    docs.reverse()
    totals = [d["stages"]["total_ms"] for d in docs]
    grand = sum(totals) or 1
    print(f"===== {len(docs)} assistant requests =====")
    print(f"total latency  mean {statistics.mean(totals):8.0f} ms   p50 {pct(totals, 50):8.0f} ms   "
          f"p95 {pct(totals, 95):8.0f} ms   p99 {pct(totals, 99):8.0f} ms\n")
    print(f"{'stage':12} {'mean ms':>10} {'p50 ms':>10} {'p95 ms':>10} {'share':>8}")
    shares = {}
    for stage in STAGES:
        values = [d["stages"][stage] for d in docs]
        shares[stage] = 100 * sum(values) / grand
        print(f"{stage.replace('_ms', ''):12} {statistics.mean(values):10.1f} "
              f"{pct(values, 50):10.1f} {pct(values, 95):10.1f} {shares[stage]:7.1f}%")
    dominant = max(shares, key=shares.get)
    print(f"\nDOMINANT STAGE: {dominant.replace('_ms', '')} "
          f"({shares[dominant]:.1f}% of all assistant latency)")
    statuses = {}
    for d in docs:
        statuses[d["status"]] = statuses.get(d["status"], 0) + 1
    print(f"statuses: {statuses}")
    tokens = [d.get("attributes", {}).get("tokens") for d in docs if d.get("attributes", {}).get("tokens")]
    if tokens:
        print(f"tokens per request: mean {statistics.mean(tokens):.0f}, max {max(tokens)}")

    ok = next((d for d in reversed(docs) if d["status"] == "completed"), None)
    bad = next((d for d in reversed(docs) if d["status"] not in ("completed", "pending_confirmation")),
               None) or db.traces.find_one({"service": "p15-assistant",
                                            "status": {"$nin": ["completed", "pending_confirmation", "ok"]}},
                                           sort=[("at", -1)])
    print("\n===== one successful trace =====")
    timeline(ok) if ok else print("(none)")
    print("\n===== one failed trace =====")
    timeline(bad) if bad else print("(none in this window: try a request while Ollama is stopped)")
    if bad:
        related = list(db.traces.find({"trace_id": bad["trace_id"], "_id": {"$ne": bad["_id"]}}))
        for r in related:
            print(f"  continued in {r['service']}: status {r['status']}")


def show(args):
    from services.common.mongo import database
    for doc in database().traces.find({"trace_id": args.trace_id}).sort("at", 1):
        timeline(doc)
        print()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("load")
    p.add_argument("--base", default="http://localhost:9150")
    p.add_argument("--email", default="p15.student.0001@example.com")
    p.add_argument("--password", default="Pair15SeedPassword!")
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--concurrency", type=int, default=1)
    p.set_defaults(func=load)
    p = sub.add_parser("report")
    p.add_argument("--last", type=int, default=50)
    p.set_defaults(func=report)
    p = sub.add_parser("show")
    p.add_argument("trace_id")
    p.set_defaults(func=show)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
