import sys
from collections import Counter

import app.assistant.loop as loop
from app.assistant.loop import run_assistant


PROMPTS = [
    "Find an internship in my city.",
    "Find a remote data science internship.",
    "Find an event for computer science students next month.",
    "Find a job in Palo Alto.",
    "Show me the details for one of the jobs from the previous results.",
    "Find internship jobs in Sunnyvale.",
    "Find remote internship jobs.",
    "Find upcoming events in Palo Alto.",
    "Find events for computer science students.",
    "Find jobs paying at least 90000.",
    "Find a quantum computing job at a nonexistent company.",
    "Find jobs at a company that does not exist.",
    "Find a biology internship in an unknown city.",
    "Find a cybersecurity event next month.",
    "From the previous job results, show higher-paying options.",
    "Find jobs with Python skills.",
    "Find part-time jobs in Cupertino.",
    "Find an on-campus job.",
    "Find events in Sunnyvale.",
    "Find a data analytics internship.",
]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "after"

    if mode == "before":
        loop.MAX_REPAIRS = 0
        loop.MAX_TEXT_REPAIRS = 0
    elif mode == "after":
        loop.MAX_REPAIRS = 1
        loop.MAX_TEXT_REPAIRS = 1
    else:
        print("Usage: python -m app.assistant.reliability_run before|after")
        raise SystemExit(2)

    conversation = []
    completed = 0
    iteration_limits = 0
    total_tool_calls = 0
    failure_counts = Counter()

    for turn_number, prompt in enumerate(PROMPTS, start=1):
        print(f"\n===== TURN {turn_number} =====")
        print(f"USER: {prompt}")

        result = run_assistant(
            user_message=prompt,
            conversation=conversation,
            student_id=1,
        )

        conversation = result.get("conversation", conversation)

        failures = result.get("failures", [])
        for failure in failures:
            failure_counts[failure] += 1

        if result["status"] == "completed":
            completed += 1
        if result["status"] == "iteration_limit":
            iteration_limits += 1

        total_tool_calls += result.get("tool_calls", 0)

        print(f"STATUS: {result['status']}")
        print(f"FAILURES: {failures}")
        print(f"TOOL_CALLS: {result['tool_calls']}")
        print(f"ANSWER: {result['answer']}")

    print("\n===== RELIABILITY SUMMARY =====")
    print(f"MODE: {mode}")
    print(f"TOTAL_TURNS: {len(PROMPTS)}")
    print(f"COMPLETED: {completed}")
    print(f"ITERATION_LIMITS: {iteration_limits}")
    print(f"TOTAL_TOOL_CALLS: {total_tool_calls}")
    print(f"MALFORMED_ARGUMENTS: {failure_counts['malformed_arguments']}")
    print(f"UNKNOWN_TOOL: {failure_counts['unknown_tool']}")
    print(
        "TEXT_INSTEAD_OF_TOOL: "
        f"{failure_counts['text_instead_of_tool']}"
    )
    print(f"CHAIN_LOST: {failure_counts['chain_lost']}")
    print(
        "WELL_FORMED_AND_CORRECT: "
        f"{len(PROMPTS) - sum(failure_counts.values())}"
    )


if __name__ == "__main__":
    main()