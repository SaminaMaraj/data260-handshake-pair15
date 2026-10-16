"""
Test 4: follow-up in the same conversation.

Run from the backend folder:
    python -m app.assistant.followup_test
"""
from app.assistant.loop import run_assistant


STUDENT_ID = 1

FIRST_REQUEST = "Find internships in Sunnyvale."
FOLLOW_UP = "From those results, show me the higher-paying options."


def main():
    print("===== TURN 1 =====")
    print(f"USER: {FIRST_REQUEST}")

    first = run_assistant(
        user_message=FIRST_REQUEST,
        student_id=STUDENT_ID,
    )

    print(f"STATUS: {first['status']}")
    print(f"FAILURES: {first['failures']}")
    print(f"ANSWER: {first['answer']}")

    print("\n===== TURN 2 (same conversation) =====")
    print(f"USER: {FOLLOW_UP}")

    second = run_assistant(
        user_message=FOLLOW_UP,
        conversation=first["conversation"],
        student_id=STUDENT_ID,
    )

    print(f"STATUS: {second['status']}")
    print(f"FAILURES: {second['failures']}")
    print(f"ANSWER: {second['answer']}")


if __name__ == "__main__":
    main()
