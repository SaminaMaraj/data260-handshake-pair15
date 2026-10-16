def confirm_action(
    tool_name,
    arguments,
    auto_approve=False,
):
    """
    Ask the student for explicit confirmation before saving.

    The model's confirmed value is not trusted.
    """

    if tool_name != "save_job_or_event":
        return True

    if auto_approve:
        return True

    job_id = arguments.get("job_id")
    event_id = arguments.get("event_id")

    item_type = "job" if job_id is not None else "event"
    item_id = job_id if job_id is not None else event_id

    try:
        answer = input(
            f"Save {item_type} {item_id}? Type yes or no: "
        ).strip().lower()
    except EOFError:
        return False

    return answer in {"yes", "y"}