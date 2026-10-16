def confirm_action(
    tool_name,
    arguments,
    auto_approve=False,
):
    """
    Require explicit confirmation before saving a job or event.
    """
    if tool_name != "save_job_or_event":
        return True

    if auto_approve:
        return True

    return arguments.get("confirmed") is True