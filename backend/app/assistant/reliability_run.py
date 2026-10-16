from app.assistant.loop import run_assistant


PROMPTS = [
    "Find an internship in my city.",
    "Find a remote data science internship.",
    "Find an event for computer science students next month.",
    "Find a job in Palo Alto.",
    "Show me the details for job 1.",
    "Find internship jobs in Sunnyvale.",
    "Find remote internship jobs.",
    "Find upcoming events in Palo Alto.",
    "Find events for computer science students.",
    "Find jobs paying at least 90000.",
    "Find a quantum computing job at Nonexistent Labs.",
    "Find jobs at a company called No Such Company.",
    "Find a biology internship in an unknown city.",
    "Find a cybersecurity event next month.",
    "Find a higher-paying option from the previous results.",
    "Find jobs with Python skills.",
    "Find part-time jobs in Cupertino.",
    "Find an on-campus job.",
    "Find events in Sunnyvale.",
    "Find a data analytics internship.",
]


def main():
    completed = 0
    iteration_limits = 0
    total_tool_calls = 0

    for turn_number, prompt in enumerate(PROMPTS, start=1):
        print(f"\n===== TURN {turn_number} =====")
        print(f"USER: {prompt}")

        result = run_assistant(
            user_message=prompt,
            student_id=1,
        )

        print(f"STATUS: {result['status']}")
        print(f"TOOL_CALLS: {result['tool_calls']}")
        print(f"ANSWER: {result['answer']}")

        total_tool_calls += result["tool_calls"]

        if result["status"] == "completed":
            completed += 1
        else:
            iteration_limits += 1

    print("\n===== RELIABILITY SUMMARY =====")
    print(f"TOTAL_TURNS: {len(PROMPTS)}")
    print(f"COMPLETED: {completed}")
    print(f"ITERATION_LIMITS: {iteration_limits}")
    print(f"TOTAL_TOOL_CALLS: {total_tool_calls}")


if __name__ == "__main__":
    main()