"""Compaction evidence with the real model (Lab 2 Part 6).

Through the gateway, as a seeded student:
  1. a multi-turn session (searches for jobs and events), printing tokens
     used and context % after every turn
  2. /compact: token counts before and after
  3. three recall questions answered from the compacted session, each
     checked automatically:
       - preferred city            must match the database
       - companies seen earlier    must name one from the session
       - "make it higher paying"   rank_jobs must reuse the earlier job ids

From backend/, with the stack and Ollama running:
    python scripts/compaction_demo.py | tee ../docs/evidence/compaction_demo.txt
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request

TURNS = [
    "Find an internship in my city.",
    "Find a remote data science internship.",
    "Find an event for computer science students next month.",
    "Show full-time jobs in Cupertino.",
]
RECALL = [
    ("city", "Without searching again, what is my preferred city?"),
    ("companies", "Which companies did we look at earlier in this session?"),
    ("follow_up", "From the last job results, make it higher paying."),
]


def post(base, path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=headers,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as err:
        sys.exit(f"{path} failed: {err.code} {err.read().decode()[:300]}")


def get(base, path, token):
    req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read())


def tools_used(result):
    return [tc["function"]["name"] for m in result["conversation"] if m.get("role") == "assistant"
            for tc in m.get("tool_calls") or []]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:9150")
    parser.add_argument("--email", default="p15.student.0001@example.com")
    parser.add_argument("--password", default="Pair15SeedPassword!")
    args = parser.parse_args()

    token = post(args.base, "/users/login", {"email": args.email, "password": args.password})["access_token"]
    session = None
    print("===== SESSION (real model) =====")
    for n, message in enumerate(TURNS, start=1):
        r = post(args.base, "/assistant/chat", {"message": message, **({"session_id": session} if session else {})}, token)
        session = r["session_id"]
        t = r["tokens"]
        print(f"\nTurn {n}: {message}\n  tools: {tools_used(r)[-3:]}  status: {r['status']}")
        print(f"  tokens this turn: {t['prompt_tokens']} prompt + {t['completion_tokens']} completion"
              f" | context {t['context_used']}/{t['context_window']} = {t['context_pct']}%"
              f"{'  WARNING > 70%' if t['warning'] else ''}  trace {r['trace_id']}")
        print("  answer: " + r["answer"][:300].replace("\n", " "))
        if r.get("compaction"):
            print(f"  AUTO-COMPACTED: {r['compaction']}")

    print("\n===== /compact =====")
    r = post(args.base, "/assistant/chat", {"message": "/compact", "session_id": session}, token)
    rep = r["compaction"]
    print(f"messages {rep['messages_before']} -> {rep['messages_after']}")
    print(f"tokens   {rep['tokens_before']} -> {rep['tokens_after']} (saved {rep['saved_pct']}%)")
    print(f"context  {rep['context_pct_before']}% -> {rep['context_pct_after']}% of the context window")
    print(f"kept last search verbatim: {rep['kept_last_search']}")

    prefs = get(args.base, "/students/me/preferences", token)
    summary_companies = set(re.findall(r"Pair 15 Company \d{4}", json.dumps(r["conversation"])))
    print("\n===== RECALL AFTER COMPACTION =====")
    checks = []
    for kind, question in RECALL:
        r = post(args.base, "/assistant/chat", {"message": question, "session_id": session}, token)
        used = tools_used(r)
        print(f"\nQ: {question}\n  tools: {used[-3:]}  status: {r['status']}  "
              f"context {r['tokens']['context_pct']}%\n  A: {r['answer'][:400]}")
        if kind == "city":
            ok = bool(prefs.get("preferred_city")) and prefs["preferred_city"].lower() in r["answer"].lower()
            checks.append((f"recalls preferred city ({prefs.get('preferred_city')})", ok))
        elif kind == "companies":
            named = summary_companies & set(re.findall(r"Pair 15 Company \d{4}", r["answer"]))
            checks.append((f"names companies from the session ({len(named)} matched)", bool(named)))
        else:
            rejected = any(e["guardrail"] == "G2" for e in r.get("guardrails", []))
            checks.append(("follow-up ranks the earlier results (rank_jobs, ids accepted)",
                           "rank_jobs" in used and not rejected))
    print("\n===== CHECKS =====")
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\nRESULT: {sum(ok for _, ok in checks)}/{len(checks)} recall checks passed")


if __name__ == "__main__":
    main()
