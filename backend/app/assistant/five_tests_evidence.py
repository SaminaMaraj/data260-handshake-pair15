"""
Evidence run for the five required Lab 1 assistant tests (Part B, item 4).

Run from the backend folder with MySQL and Ollama running:
    python -m app.assistant.five_tests_evidence

Every test goes through the existing run_assistant() / OllamaClient path.
This file never calls a tool itself and never changes tool arguments.
The loop already prints TOOL_CALL, TOOL_RESULT, REPAIR and
TOTAL_TOOL_CALLS lines; this runner adds the test headers, the result
fields, and a short check of what the transcript shows for each rubric
requirement. Failures are printed as they happen; nothing is retried.

Test wording follows the handout:
  1. Find an internship in my city.
  2. Find a remote data science internship.
  3. Find an event for computer science students next month.
  4. Follow-up in the same conversation: make it closer or higher paying.
  5. Ask for a job category or company absent from the seed data.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

import app.assistant.loop as loop
from app.assistant.client import OllamaClient
from app.assistant.loop import run_assistant
from app.database import SessionLocal
from app.models.additional import StudentPreference
from app.models.core import Company


ABSENT_COMPANY = "Nonexistent Labs"

TEST_1 = "Find an internship in my city."
TEST_2 = "Find a remote data science internship."
TEST_3 = "Find an event for computer science students next month."
TEST_4 = "Make it higher paying."
TEST_5 = f"Find a job at {ABSENT_COMPANY}."


def git_commit() -> str:
    try:
        root = Path(__file__).resolve().parents[3]
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def pick_student() -> tuple[int, str]:
    """The lowest student ID that has saved preferences with a city."""
    db = SessionLocal()
    try:
        row = db.execute(
            select(StudentPreference.student_id, StudentPreference.preferred_city)
            .where(StudentPreference.preferred_city.is_not(None))
            .order_by(StudentPreference.student_id.asc())
            .limit(1)
        ).first()
        if row is None:
            raise SystemExit("No student has saved preferences with a city.")
        return row[0], row[1]
    finally:
        db.close()


def company_count(name: str) -> int:
    db = SessionLocal()
    try:
        return db.scalar(
            select(func.count())
            .select_from(Company)
            .where(Company.company_name.ilike(f"%{name}%"))
        )
    finally:
        db.close()


def tool_calls_in(conversation: list[dict], start: int = 0) -> list[tuple[str, dict]]:
    """Tool calls the model requested, read from the returned conversation."""
    calls = []
    for message in conversation[start:]:
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"_raw": arguments}
            calls.append((function.get("name", ""), arguments))
    return calls


def run_test(number: int, title: str, message: str, student_id: int,
             conversation: list[dict] | None = None) -> dict:
    conversation = conversation or []
    print("\n" + "=" * 70)
    print(f"TEST {number}: {title}")
    print("=" * 70)
    print(f"USER: {message}")
    print(f"CONVERSATION MESSAGES PASSED IN: {len(conversation)}")

    result = run_assistant(
        user_message=message,
        conversation=conversation,
        student_id=student_id,
    )

    print(f"STATUS: {result['status']}")
    print(f"FAILURES: {result.get('failures', [])}")
    print(f"TOOL_CALLS: {result['tool_calls']}")
    print(f"ITERATIONS: {result['iterations']}")
    print("FINAL ANSWER:")
    print(result["answer"])

    result["_new_calls"] = tool_calls_in(result["conversation"], len(conversation))
    return result


def check(label: str, passed: bool) -> None:
    print(f"RUBRIC CHECK [{'yes' if passed else 'no'}] {label}")


def main():
    student_id, city = pick_student()
    absent = company_count(ABSENT_COMPANY)

    print("DATA260 Lab 1 Pair 15: five required assistant tests")
    print(f"Run at: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Git commit: {git_commit()}")
    print(f"Model: {OllamaClient().model}")
    print(f"MAX_ITERATIONS={loop.MAX_ITERATIONS} MAX_REPAIRS={loop.MAX_REPAIRS} "
          f"MAX_TEXT_REPAIRS={loop.MAX_TEXT_REPAIRS} WRAP_UNTRUSTED={loop.WRAP_UNTRUSTED}")
    print(f"Student: lowest student_id with saved preferences = {student_id} "
          f"(preferred city: {city})")
    print(f"Companies matching '{ABSENT_COMPANY}' in the database: {absent}")

    # Test 1
    r1 = run_test(1, "Internship in the student's city", TEST_1, student_id)
    names1 = [name for name, _ in r1["_new_calls"]]
    check("get_student_preferences was the first tool call",
          bool(names1) and names1[0] == "get_student_preferences")
    check("a search_jobs call used the preferred city",
          any(name == "search_jobs" and str(args.get("city", "")).lower() == str(city).lower()
              for name, args in r1["_new_calls"]))

    # Test 2
    r2 = run_test(2, "Remote data science internship", TEST_2, student_id)
    jobs2 = [args for name, args in r2["_new_calls"] if name == "search_jobs"]
    check("search_jobs filtered by category", any(a.get("category") for a in jobs2))
    check("search_jobs filtered by location or remote status",
          any(a.get("remote_only") or a.get("city") for a in jobs2))
    check("search_jobs filtered by skills", any(a.get("skill") for a in jobs2))

    # Test 3
    r3 = run_test(3, "Computer science event next month", TEST_3, student_id)
    events3 = [args for name, args in r3["_new_calls"] if name == "search_events"]
    check("search_events filtered by date",
          any(a.get("date_from") or a.get("date_to") for a in events3))
    check("search_events filtered by eligibility or major",
          any(a.get("eligibility") or a.get("major") for a in events3))
    check("search_events used the major parameter", any(a.get("major") for a in events3))

    # Test 4: same conversation as test 1
    r4 = run_test(4, "Follow-up in the same conversation (higher paying)", TEST_4,
                  student_id, conversation=r1["conversation"])
    names4 = [name for name, _ in r4["_new_calls"]]
    check("test 1 conversation was passed in", len(r1["conversation"]) > 0)
    check("the follow-up called rank_jobs or search_jobs",
          any(n in ("rank_jobs", "search_jobs") for n in names4))

    # Test 5
    r5 = run_test(5, "Company absent from the seed data", TEST_5, student_id)
    check(f"'{ABSENT_COMPANY}' is absent from the database", absent == 0)
    check("a search tool was called before answering",
          any(n in ("search_jobs", "get_job_details") for n, _ in r5["_new_calls"]))

    results = [r1, r2, r3, r4, r5]
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for number, result in enumerate(results, start=1):
        print(f"TEST {number}: status={result['status']} "
              f"tool_calls={result['tool_calls']} failures={result.get('failures', [])}")
    print(f"TESTS RUN: {len(results)}")
    print(f"TOTAL TOOL CALLS: {sum(r['tool_calls'] for r in results)}")


if __name__ == "__main__":
    main()
