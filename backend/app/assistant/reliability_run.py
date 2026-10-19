import json
import re
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


# Prompts that need two or more tool steps in order. Used only to
# measure lost chains; the assistant loop never sees this table.
CHAIN_RULES = {
    "Find an internship in my city.": "preferences_then_search",
    "Show me the details for one of the jobs from the previous results.":
        "details_from_previous_results",
    "From the previous job results, show higher-paying options.":
        "rank_previous_results",
}


def _executed_tools(messages: list[dict]) -> list[tuple[str, str]]:
    """(tool_name, content) for tool results that actually ran."""
    executed = []
    for message in messages:
        if message.get("role") != "tool":
            continue
        content = str(message.get("content", ""))
        if content.startswith("TOOL ERROR"):
            continue
        executed.append((message.get("tool_name", ""), content))
    return executed


def _requested_calls(messages: list[dict]) -> list[tuple[str, dict]]:
    calls = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            calls.append((function.get("name", ""), arguments))
    return calls


def _job_ids_from_searches(messages: list[dict]) -> set[int]:
    ids = set()
    for name, content in _executed_tools(messages):
        if name == "search_jobs":
            ids.update(int(x) for x in re.findall(r'"job_id"\s*:\s*(\d+)', content))
    return ids


# A tool that runs with an argument it does not accept (for example
# search_jobs(minimum_salary=...)) returns "Tool execution error: ...
# unexpected keyword argument ...". The loop only checks that arguments
# are a JSON object, so it does not record these. The runner records each
# one as malformed_arguments.
INVALID_ARGUMENT_ERROR = re.compile(
    r"Tool execution error: .*("
    r"unexpected keyword argument|"
    r"missing \d+ required (positional |keyword-only )?argument)"
)


def invalid_argument_errors(turn: list[dict]) -> int:
    """Number of tool results in this turn caused by an invalid argument."""
    return sum(
        1
        for message in turn
        if message.get("role") == "tool"
        and INVALID_ARGUMENT_ERROR.search(str(message.get("content", "")))
    )


def chain_lost(rule: str | None, earlier: list[dict], turn: list[dict]) -> bool:
    """
    True when a multi-step turn started using tools but did not finish
    the required steps. Turns with no tool calls at all are already
    counted as text_instead_of_tool, so they are not counted here.
    """
    if rule is None:
        return False

    executed = _executed_tools(turn)
    if not _requested_calls(turn):
        return False

    names = [name for name, _ in executed]

    if rule == "preferences_then_search":
        if "get_student_preferences" not in names:
            return True
        first = names.index("get_student_preferences")
        return "search_jobs" not in names[first + 1:]

    if rule == "details_from_previous_results":
        previous_ids = _job_ids_from_searches(earlier)
        for name, arguments in _requested_calls(turn):
            if name == "get_job_details" and arguments.get("job_id") in previous_ids:
                return "get_job_details" not in names
        return True

    if rule == "rank_previous_results":
        if "rank_jobs" in names:
            return False
        return not any(
            name == "search_jobs" and arguments.get("salary_min") is not None
            for name, arguments in _requested_calls(turn)
        )

    return False


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
    well_formed_turns = 0

    for turn_number, prompt in enumerate(PROMPTS, start=1):
        print(f"\n===== TURN {turn_number} =====")
        print(f"USER: {prompt}")

        earlier = list(conversation)

        result = run_assistant(
            user_message=prompt,
            conversation=conversation,
            student_id=1,
        )

        conversation = result.get("conversation", conversation)
        turn_messages = conversation[len(earlier):]

        failures = list(result.get("failures", []))
        failures.extend(
            ["malformed_arguments"] * invalid_argument_errors(turn_messages)
        )

        rule = CHAIN_RULES.get(prompt)
        if chain_lost(rule, earlier, turn_messages):
            failures.append("chain_lost")

        for failure in failures:
            failure_counts[failure] += 1

        if result["status"] == "completed":
            completed += 1
        if result["status"] == "iteration_limit":
            iteration_limits += 1

        if result["status"] == "completed" and not failures:
            well_formed_turns += 1

        total_tool_calls += result.get("tool_calls", 0)

        print(f"STATUS: {result['status']}")
        if rule:
            print(f"CHAIN_RULE: {rule}")
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
    print(f"CHAIN_TURNS_MEASURED: {len(CHAIN_RULES)}")
    print(f"CHAIN_LOST: {failure_counts['chain_lost']}")
    print(f"WELL_FORMED_AND_CORRECT: {well_formed_turns}")


if __name__ == "__main__":
    main()
