"""Hand-built agent loop with the eight Lab 2 guardrails.

No agent framework: the model gets the system prompt (all three memory
layers), the conversation and the tool schemas; it either answers or asks
for tools; this code checks each tool call, runs it, returns string results,
and repeats until a final answer or a bounded stop.

Per tool call, in this order (guardrail ids from services/assistant/guardrails.py):

    G1 allowlist -> parse JSON -> G3 drop app-owned args, scope to the JWT
    student -> G2 strict schema -> semantic checks (job ids from the last
    search, date order) -> G4 write tools need confirmation -> execute
    (G7: one retry for a failed tool) -> G6 redact secrets -> G5 remove
    instruction-like text, wrap as untrusted data

Per run: G7 request deadline and MAX_ITERATIONS; an invalid call gets ONE
repair re-prompt; an answer without a tool call gets ONE nudge. The final
answer passes G6 (secrets, other people's e-mail) and G8 (grounding).

Every run returns guardrail events and per-stage timing (model, tools,
database) so tracing and the evaluation harness can report them.
"""
import html
import json
import os
import re
import secrets
import time
from datetime import date, timedelta

from services.assistant import guardrails as g
from services.assistant.agent.client import OllamaClient
from services.assistant.agent.tools import TOOL_SCHEMAS, execute_tool
from services.assistant.memory import build_system_prompt
from services.common.mongo import PENDING_ACTIONS, USERS, database, utcnow
from services.common.mongo import PENDING_TTL_SECONDS as MONGO_PENDING_TTL_SECONDS

MAX_ITERATIONS = 6

# Repair path: an invalid tool call is re-prompted ONCE with the specific
# error, then the run stops cleanly. 0 = the "before repair" measurement.
MAX_REPAIRS = 1
# One nudge when the model answers in text without calling any tool.
MAX_TEXT_REPAIRS = 1
# G7: at most one automatic retry of a tool that failed with an exception.
MAX_TOOL_RETRIES = 1
# G7: whole request budget in seconds (model calls included).
REQUEST_TIMEOUT_SECONDS = float(os.getenv("ASSISTANT_TIMEOUT_SECONDS", "150"))

# G5 switches; both False = the "before defense" injection measurement.
WRAP_UNTRUSTED = True
SANITIZE_UNTRUSTED = True

g.load_schemas(TOOL_SCHEMAS)
KNOWN_TOOLS = set(g.TOOL_POLICY)
VALID_CATEGORIES = {"full_time", "part_time", "on_campus", "internship"}
PENDING_TTL_SECONDS = MONGO_PENDING_TTL_SECONDS

MODEL_UNAVAILABLE = ("The assistant model is unavailable right now, so I can't "
                     "answer reliably. Please try again in a minute.")


def _system_prompt(student_id: int | None = None) -> str:
    """Rules (assistant_rules) + learned memory (student_memory); the
    session layer is the message history that follows."""
    return build_system_prompt(database(), student_id)


def _log(line: str) -> None:
    print(g.redact(line)[0])  # G6: no secrets in service logs


# ---- argument handling ------------------------------------------------------------------

def _parse_arguments(arguments):
    if isinstance(arguments, dict):
        return dict(arguments), None
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}, "Arguments were not valid JSON."
        if not isinstance(parsed, dict):
            return {}, "Tool arguments must be a JSON object."
        return parsed, None
    return {}, "Tool arguments must be a JSON object."


def _latest_search_job_ids(messages: list[dict]) -> list[int]:
    """Job ids from the most recent search_jobs result (database output only)."""
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("tool_name") != "search_jobs":
            continue
        content = html.unescape(str(message.get("content", "")))
        ids = []
        for match in re.findall(r'"job_id"\s*:\s*(\d+)', content):
            if int(match) not in ids:
                ids.append(int(match))
        return ids
    return []


def _semantic_error(tool_name: str, arguments: dict, messages: list[dict]):
    """Checks a JSON schema cannot express."""
    if tool_name == "rank_jobs":
        valid = _latest_search_job_ids(messages)
        if not valid:
            return "There are no job IDs from a previous search_jobs result. Call search_jobs first."
        invalid = [j for j in arguments["job_ids"] if j not in valid]
        if invalid:
            return (f"These job IDs were not in the most recent search_jobs result: {invalid}. "
                    "Only the job_id values on the JOB_IDS line are valid. Numbers inside "
                    "company names or job titles are not job IDs. Call rank_jobs again "
                    f"using only these IDs: {valid}.")
    if tool_name == "search_events":
        start, end = arguments.get("date_from"), arguments.get("date_to")
        for name, value in (("date_from", start), ("date_to", end)):
            if value is not None:
                try:
                    date.fromisoformat(value)
                except ValueError:
                    return f"{name} is not a real calendar date."
        if start and end and start > end:
            return "date_from cannot be later than date_to."
    if tool_name == "search_jobs" and arguments.get("deadline_before"):
        try:
            date.fromisoformat(arguments["deadline_before"])
        except ValueError:
            return "deadline_before is not a real calendar date."
    return None


def _wrap_untrusted_result(tool_name: str, result: str, events: list | None = None) -> str:
    """G5: remove instruction-like sentences, then label and delimit the data."""
    text = str(result)
    if SANITIZE_UNTRUSTED:
        text, found = g.sanitize_untrusted(text)
        if found and events is not None:
            events.append(g.event("G5", "prompt_injection", "removed",
                                  f"{len(found)} instruction-like sentence(s) removed from "
                                  f"{tool_name} result", removed=found))
    return g.wrap_untrusted(tool_name, text) if WRAP_UNTRUSTED else text


# ---- pending confirmations (G4) -----------------------------------------------------------

def _store_pending_action(action: dict) -> str:
    pending_id = secrets.token_urlsafe(16)
    now = utcnow()
    database()[PENDING_ACTIONS].insert_one({
        "_id": pending_id, **action, "created_at": now,
        "expires_at": now + timedelta(seconds=PENDING_TTL_SECONDS)})
    return pending_id


def _claim_pending_action(pending_id: str, student_id: int):
    """(status, action); find_one_and_delete makes each id usable once,
    even with several assistant replicas."""
    collection = database()[PENDING_ACTIONS]
    live = {"_id": pending_id, "expires_at": {"$gt": utcnow()}}
    action = collection.find_one(live, {"student_id": 1})
    if action is None:
        return "invalid_pending", None
    if action["student_id"] != student_id:
        return "forbidden", None  # left in place for its real owner
    action = collection.find_one_and_delete({**live, "student_id": student_id})
    return ("ok", action) if action else ("invalid_pending", None)


def _pending_result(result: str):
    try:
        data = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("status") == "pending_confirmation" else None


def _clean_conversation(conversation) -> list[dict]:
    """A client cannot add its own system prompt: keep user/assistant/tool only."""
    return [m for m in conversation or []
            if isinstance(m, dict) and m.get("role") in {"user", "assistant", "tool"}]


def _own_email(student_id: int):
    try:
        doc = database()[USERS].find_one({"_id": student_id}, {"email": 1})
        return doc and doc.get("email")
    except Exception:
        return None


# ---- the run state ------------------------------------------------------------------------

class Run:
    """Counters, guardrail events and stage timings for one request."""

    def __init__(self, student_id, client, tool_call_count=0):
        self.student_id = student_id
        self.client = client
        self.tool_call_count = tool_call_count
        self.failures: list[str] = []
        self.events: list[dict] = []
        self.repairs = 0
        self.text_repairs = 0
        self.tool_retries = 0
        self.deadline = g.Deadline(REQUEST_TIMEOUT_SECONDS)
        self.started = time.perf_counter()
        self.timing = {"model_ms": 0.0, "tool_ms": 0.0, "model_calls": 0, "tool_runs": 0,
                       "spans": []}

    def span(self, stage: str, name: str, started: float, **extra):
        ms = round((time.perf_counter() - started) * 1000, 1)
        self.timing[f"{stage}_ms"] = round(self.timing[f"{stage}_ms"] + ms, 1)
        self.timing[f"{stage}_calls" if stage == "model" else "tool_runs"] += 1
        self.timing["spans"].append({"stage": stage, "name": name, "ms": ms, **extra})

    def model(self, messages):
        if hasattr(self.client, "timeout"):
            self.client.timeout = max(1.0, min(180.0, self.deadline.remaining()))
        started = time.perf_counter()
        reply = self.client.complete(messages=messages, tools=TOOL_SCHEMAS)
        self.span("model", "chat", started)
        return reply

    def tool(self, tool_name, arguments):
        started = time.perf_counter()
        result = execute_tool(tool_name=tool_name, arguments=arguments)
        self.span("tool", tool_name, started)
        return result


def _finish(run: Run, answer, messages, iterations, status, assistant_message=None, extra=None):
    _log(f"TOTAL_TOOL_CALLS {run.tool_call_count}")
    conversation = messages[1:] + ([assistant_message] if assistant_message else [])
    total_ms = round((time.perf_counter() - run.started) * 1000, 1)
    result = {
        "answer": answer, "conversation": conversation, "tool_calls": run.tool_call_count,
        "iterations": iterations, "status": status, "failures": run.failures,
        "guardrails": run.events, "repairs": run.repairs, "tool_retries": run.tool_retries,
        "timing": {**run.timing, "total_ms": total_ms,
                   "other_ms": round(total_ms - run.timing["model_ms"] - run.timing["tool_ms"], 1)},
    }
    if extra:
        result.update(extra)
    return result


def _final_answer(run: Run, answer: str, messages: list[dict]):
    """G6 redaction and G8 grounding on the text the student will read."""
    answer, kinds = g.redact(answer or "", own_email=_own_email(run.student_id), emails=True)
    if kinds:
        run.events.append(g.event("G6", "privacy", "redacted", "removed from the answer: "
                                  + ", ".join(kinds)))
    tool_texts = [str(m.get("content", "")) for m in messages
                  if m.get("role") == "tool" and not str(m.get("content", "")).startswith("TOOL ERROR")]
    check = g.grounding_check(answer, tool_texts)
    if check:
        run.events.append(check)
        run.failures.append("ungrounded_answer")
        if check["action"] == "replaced":
            return g.UNGROUNDED_REPLACEMENT
        answer += ("\n\n(Note: I could not verify these against the database, so treat "
                   "them as unconfirmed: " + ", ".join(check["unverified"]) + ".)")
    return answer


# ---- the core loop -------------------------------------------------------------------------

def _repair_or_stop(run, messages, tool_name, failure_type, guard_event, iteration):
    """Record a rejected call; re-prompt once (G7) or stop cleanly."""
    run.failures.append(failure_type)
    run.events.append(guard_event)
    _log(f"GUARDRAIL {guard_event['guardrail']} {guard_event['action']}: {guard_event['detail']}")
    if run.repairs >= MAX_REPAIRS:
        return _finish(run, "I could not complete the request because the tool call was "
                       f"still invalid after {MAX_REPAIRS} correction attempt(s): "
                       f"{guard_event['detail']}", messages, iteration + 1, "repair_failed")
    run.repairs += 1
    messages.append({"role": "tool", "tool_name": tool_name or "unknown",
                     "content": f"TOOL ERROR: {guard_event['detail']} Correct the call and "
                                "try again."})
    return None


def _agent_loop(messages, run: Run, declined_items=None, allow_text_repair=True):
    declined_items = declined_items or set()
    if not allow_text_repair:
        run.text_repairs = MAX_TEXT_REPAIRS

    for iteration in range(MAX_ITERATIONS):
        if run.deadline.expired():  # G7
            run.events.append(g.event("G7", "bounded_execution", "stopped",
                                      f"request deadline of {REQUEST_TIMEOUT_SECONDS:.0f}s reached"))
            run.failures.append("timeout")
            return _finish(run, "I ran out of time for this request before finishing. "
                           "Please try a narrower question.", messages, iteration, "timeout")

        assistant_message = run.model(messages)
        content = assistant_message.get("content") or ""
        if content.startswith("Ollama request failed"):  # G7: never pass errors off as answers
            run.events.append(g.event("G7", "bounded_execution", "stopped",
                                      g.redact(content)[0][:200]))
            run.failures.append("model_error")
            return _finish(run, MODEL_UNAVAILABLE, messages, iteration + 1, "model_error")

        tool_calls = assistant_message.get("tool_calls") or []
        if not tool_calls:
            first_text = iteration == 0 and run.tool_call_count == 0 and allow_text_repair
            if first_text and run.text_repairs < MAX_TEXT_REPAIRS:
                run.text_repairs += 1
                run.failures.append("text_instead_of_tool")
                _log("REPAIR text_instead_of_tool: re-prompting once")
                messages.append(assistant_message)
                messages.append({"role": "user", "content": (
                    "[Assistant loop correction] You answered without calling a tool. If this "
                    "request is about jobs, companies, events, preferences, or saved items, "
                    "call the correct tool now. Otherwise, repeat your answer.")})
                continue
            if first_text and MAX_TEXT_REPAIRS == 0:
                run.failures.append("text_instead_of_tool")
            answer = _final_answer(run, content or "The assistant did not return an answer.",
                                   messages)
            return _finish(run, answer, messages, iteration + 1, "completed",
                           {**assistant_message, "content": answer})

        messages.append(assistant_message)
        for tool_call in tool_calls:
            function = tool_call.get("function", {}) or {}
            tool_name = function.get("name", "") or ""
            raw_args, parse_error = _parse_arguments(function.get("arguments", {}))
            run.tool_call_count += 1
            _log(f"TOOL_CALL {tool_name or 'unknown'} {json.dumps(raw_args, default=str)}")

            blocked = g.check_allowlist(tool_name)                                   # G1
            failure = "unknown_tool"
            if not blocked and parse_error:
                blocked = g.event("G2", "schema_validation", "rejected", parse_error)
                failure = "malformed_arguments"
            if not blocked:
                arguments, auth_events = g.enforce_app_owned(tool_name, raw_args,    # G3
                                                             run.student_id)
                run.events += auth_events
                model_args = {k: v for k, v in arguments.items() if k != "student_id"}
                blocked = g.validate_schema(tool_name, model_args)                    # G2
                failure = "malformed_arguments"
                if not blocked:
                    problem = _semantic_error(tool_name, model_args, messages)
                    if problem:
                        blocked = g.event("G2", "semantic_validation", "rejected", problem)
            if blocked:
                stop = _repair_or_stop(run, messages, tool_name, failure, blocked, iteration)
                if stop:
                    return stop
                continue

            if g.is_write(tool_name):                                                 # G4
                item = (("job", arguments["job_id"]) if arguments.get("job_id") is not None
                        else ("event", arguments.get("event_id")))
                if item in declined_items:
                    result = f"The student already declined saving {item[0]} {item[1]}; do not retry."
                    run.events.append(g.event("G4", "read_write_control", "blocked",
                                              "retry of a declined save"))
                    _log(f"TOOL_RESULT {result}")
                    messages.append({"role": "tool", "tool_name": tool_name, "content": result})
                    continue

            result = run.tool(tool_name, arguments)
            if g.is_recoverable_tool_error(result) and run.tool_retries < MAX_TOOL_RETRIES:
                run.tool_retries += 1                                                 # G7
                run.events.append(g.event("G7", "bounded_execution", "retried",
                                          f"{tool_name} failed once; retrying: {result[:120]}"))
                result = run.tool(tool_name, arguments)
            _log(f"TOOL_RESULT {result}")

            pending = _pending_result(result) if g.is_write(tool_name) else None
            if pending is not None:
                run.events.append(g.event("G4", "read_write_control", "confirmation_required",
                                          pending["label"]))
                pending_id = _store_pending_action({
                    "student_id": run.student_id, "tool_name": tool_name,
                    "arguments": dict(arguments), "item_type": pending["item_type"],
                    "item_id": pending["item_id"], "label": pending["label"],
                    "conversation": messages[1:], "tool_call_count": run.tool_call_count})
                _log(f"PENDING_CONFIRMATION {pending_id} {pending['label']}")
                return _finish(run, pending["label"], messages, iteration + 1,
                               "pending_confirmation",
                               extra={"pending_id": pending_id, "label": pending["label"]})

            result, kinds = g.redact(result)                                          # G6
            if kinds:
                run.events.append(g.event("G6", "privacy", "redacted",
                                          f"removed from {tool_name} result: " + ", ".join(kinds)))
            messages.append({"role": "tool", "tool_name": tool_name,
                             "content": _wrap_untrusted_result(tool_name, result, run.events)})

    run.events.append(g.event("G7", "bounded_execution", "stopped",
                              f"MAX_ITERATIONS={MAX_ITERATIONS} reached"))
    run.failures.append("iteration_limit")
    return _finish(run, "I reached the assistant's safe iteration limit before completing "
                   "the request.", messages, MAX_ITERATIONS, "iteration_limit")


# ---- public entry points -------------------------------------------------------------------

def run_assistant(user_message: str, conversation=None, student_id: int = 1, client=None) -> dict:
    """Pass the "conversation" returned by the previous call to continue it."""
    client = client or OllamaClient()
    messages = [{"role": "system", "content": _system_prompt(student_id)}]
    messages += _clean_conversation(conversation)
    messages.append({"role": "user", "content": user_message})
    return _agent_loop(messages, Run(student_id, client))


def resume_pending_confirmation(pending_id: str, approve: bool, student_id: int,
                                client=None) -> dict:
    """Continue a run stopped at pending_confirmation, using only the
    arguments stored on the server (G4)."""
    status, action = _claim_pending_action(pending_id, student_id)
    if status == "invalid_pending":
        return {"status": "invalid_pending",
                "answer": "This confirmation has expired or was already used."}
    if status == "forbidden":
        return {"status": "forbidden",
                "answer": "This confirmation belongs to a different student."}

    run = Run(student_id, client or OllamaClient(), action["tool_call_count"])
    tool_name, arguments, declined = action["tool_name"], dict(action["arguments"]), set()
    if approve:
        _log(f"TOOL_CALL {tool_name} {json.dumps(arguments, default=str)} (student approved)")
        result = run.tool(tool_name, {**arguments, "auto_approve": True})
        run.tool_call_count += 1
        run.events.append(g.event("G4", "read_write_control", "approved",
                                  "the student confirmed: " + action["label"]))
        content = _wrap_untrusted_result(tool_name, result, run.events)
    else:
        result = f"Cancelled: the student declined to save {action['item_type']} {action['item_id']}."
        declined.add((action["item_type"], action["item_id"]))
        run.events.append(g.event("G4", "read_write_control", "declined",
                                  "the student declined: " + action["label"]))
        content = result  # loop-generated, not database content
    _log(f"TOOL_RESULT {result}")
    messages = [{"role": "system", "content": _system_prompt(student_id)}]
    messages += action["conversation"]
    messages.append({"role": "tool", "tool_name": tool_name, "content": content})
    return _agent_loop(messages, run, declined_items=declined, allow_text_repair=False)
