"""
Confirmation gate for state-changing assistant tools.

confirm_action returns one of three strings:

- "approved": auto_approve=True, or the student typed yes in the
  terminal
- "declined": the student typed no in the terminal
- "pending":  API mode; the website must ask the student, so no
  input() call is made inside FastAPI

Read-only tools are never gated.
"""

# "api" is the default so input() can never run inside the web server.
# Terminal test scripts set this to "terminal" before running.
CONFIRM_MODE = "api"

GATED_TOOLS = {"save_job_or_event"}


def confirm_action(
    tool_name,
    arguments,
    auto_approve=False,
):
    if tool_name not in GATED_TOOLS:
        return "approved"

    if auto_approve:
        return "approved"

    if CONFIRM_MODE != "terminal":
        return "pending"

    job_id = arguments.get("job_id")
    event_id = arguments.get("event_id")

    item_type = "job" if job_id is not None else "event"
    item_id = job_id if job_id is not None else event_id

    try:
        answer = input(
            f"Save {item_type} {item_id}? Type yes or no: "
        ).strip().lower()
    except EOFError:
        return "declined"

    return "approved" if answer in {"yes", "y"} else "declined"
