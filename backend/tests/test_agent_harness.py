"""Lab 2 Part 6: the evaluation harness passes every case.

Runs harness/agent_harness.py end to end (production loop, guardrails,
tools, MongoDB; scripted model) into a throwaway database and output folder.
Run from backend/:  python -m pytest tests/test_agent_harness.py -q
"""
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET_KEY", "harness-test-key-not-for-production-0123456789")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")

import pytest


def test_harness_all_cases_pass(tmp_path, monkeypatch):
    from services.common import mongo
    try:
        mongo.client().admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    name = f"p15_harness_test_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("HARNESS_OUTPUT", str(tmp_path))
    from harness import agent_harness as h
    monkeypatch.setattr(h, "OUT", tmp_path)
    monkeypatch.setenv("MONGO_DB", name)
    try:
        rows = h.run_all()
    finally:
        mongo.client().drop_database(name)

    failed = [(r["case"], [c for c in r["checks"] if not c["passed"]]) for r in rows if not r["passed"]]
    assert not failed, failed
    required = {"read_only_search", "accepted_state_change", "declined_state_change",
                "malformed_arguments_repaired", "unknown_tool", "no_match",
                "conversation_followup", "prompt_injection_before_defense",
                "prompt_injection_after_defense", "iteration_ceiling", "request_timeout",
                "tool_recovery_retry"}
    assert required <= {r["case"] for r in rows}

    records = [json.loads(l) for l in (tmp_path / "agent_harness.jsonl").read_text().splitlines()]
    fields = {"input", "assistant_messages", "tool_calls", "tool_results", "final_answer",
              "guardrail_outcome", "errors", "repairs", "tool_retries", "iterations",
              "tool_call_count", "elapsed_ms"}
    assert all(fields <= set(r) for r in records)
    assert (tmp_path / "agent_harness_summary.md").exists()
