"""Model arguments never constitute authenticated user approval.

Persistent approvals are issued and consumed by app.assistant.pending.
This compatibility helper can authorize only read-only tools.
"""
def confirm_action(tool_name, arguments, auto_approve=False):
    return tool_name != "save_job_or_event"
