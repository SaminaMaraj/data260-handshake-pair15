"""The eight agentic guardrails (Lab 2 Part 6), in one module.

Each check returns data, never raises, and is recorded as an event
    {"guardrail": "G2", "name": "schema_validation", "action": "rejected", "detail": ...}
so the loop's result, the service logs and the evaluation harness all show
exactly which guardrail fired.

  G1 allowlist        only declared tools run; unknown names are rejected
  G2 schema           every call is validated against its strict JSON schema
                      (types, enums, formats, bounds, no extra arguments)
  G3 authorization    app-owned arguments (student_id, auto_approve) are
                      removed from model output and set from the JWT; HTTP
                      routes enforce role and ownership (services/common/auth.py)
  G4 read/write       read tools run automatically; write tools need the
                      student's explicit confirmation (pending_actions)
  G5 injection        retrieved text is labelled and delimited as untrusted
                      data, and instruction-like sentences in it are removed
  G6 privacy/secrets  tokens, passwords, keys, hashes and other people's
                      e-mail addresses are redacted from model input,
                      answers and logs
  G7 bounded run      request deadline, hard iteration ceiling, one repair
                      for an invalid call, one retry for a failed tool
  G8 reliable answers no-match and error messages are explicit; answers that
                      name companies or salaries no tool returned are flagged
"""
import re
import time

from jsonschema import Draft202012Validator

# ---- G1 / G4: the declared tools and what each may do -----------------------------

TOOL_POLICY = {
    "get_student_preferences": "read",
    "search_jobs": "read",
    "rank_jobs": "read",
    "get_job_details": "read",
    "search_events": "read",
    "save_job_or_event": "write",
}
# Arguments the model may never set; the application fills them in.
APP_OWNED_ARGUMENTS = {"student_id", "auto_approve"}
STUDENT_SCOPED_TOOLS = {"get_student_preferences", "save_job_or_event"}


def event(guardrail: str, name: str, action: str, detail: str = "", **extra) -> dict:
    return {"guardrail": guardrail, "name": name, "action": action, "detail": detail, **extra}


def check_allowlist(tool_name: str):
    if tool_name in TOOL_POLICY:
        return None
    return event("G1", "tool_allowlist", "rejected",
                 f"Unknown tool: {tool_name or '(none)'}. Valid tools are: "
                 + ", ".join(sorted(TOOL_POLICY)) + ".")


def is_write(tool_name: str) -> bool:
    return TOOL_POLICY.get(tool_name) == "write"


# ---- G2: strict schema validation ---------------------------------------------------

_validators: dict[str, Draft202012Validator] = {}


def load_schemas(tool_schemas: list[dict]) -> None:
    for tool in tool_schemas:
        fn = tool["function"]
        _validators[fn["name"]] = Draft202012Validator(fn["parameters"])


def _describe(error) -> str:
    where = ".".join(str(p) for p in error.absolute_path)
    if error.validator == "additionalProperties":
        extra = re.findall(r"'([^']+)'", error.message)
        return (f"unexpected argument(s) {', '.join(extra) or error.message}; "
                "remove them and use only the documented parameters")
    if error.validator == "oneOf":
        return "provide exactly one of the alternatives (e.g. job_id or event_id, not both)"
    prefix = f"'{where}' " if where else ""
    return prefix + error.message


def validate_schema(tool_name: str, arguments):
    if not isinstance(arguments, dict):
        return event("G2", "schema_validation", "rejected",
                     "Tool arguments must be a JSON object.")
    validator = _validators.get(tool_name)
    if validator is None:
        return None
    errors = sorted(validator.iter_errors(arguments), key=lambda e: list(e.absolute_path))
    if not errors:
        return None
    return event("G2", "schema_validation", "rejected",
                 f"{tool_name} arguments are invalid: "
                 + "; ".join(_describe(e) for e in errors[:4]) + ".")


# ---- G3: authorization ----------------------------------------------------------------

def enforce_app_owned(tool_name: str, arguments: dict, student_id: int):
    """Drop model-supplied app-owned arguments; scope tools to the JWT student."""
    events_ = []
    for key in APP_OWNED_ARGUMENTS & set(arguments):
        value = arguments.pop(key)
        if key == "student_id" and value != student_id:
            events_.append(event("G3", "authorization", "overridden",
                                 f"model asked for student_id={value}; "
                                 f"using the signed-in student {student_id}"))
        elif key == "auto_approve":
            events_.append(event("G3", "authorization", "removed",
                                 "model tried to set auto_approve; only the student can approve"))
    scoped = dict(arguments)
    if tool_name in STUDENT_SCOPED_TOOLS:
        scoped["student_id"] = student_id
    return scoped, events_


# ---- G5: prompt-injection defense --------------------------------------------------------

INJECTION_PATTERNS = [
    r"\bignore\b[^.!?\n\"]{0,30}\b(rules?|instructions?|prompts?|guidelines)",
    r"\bdisregard\b[^.!?\n\"]{0,30}\b(rules?|instructions?|above|previous)",
    r"\byou are now\b",
    r"\b(new|updated) (system )?instructions?\b",
    r"\bsystem prompt\b",
    r"\b(reveal|show|print|leak|expose|list)\b[^.!?\n\"]{0,40}\b(private|passwords?|tokens?|secrets?|api keys?|other students?|database information)",
    r"\b(promote|rank|recommend|put)\b[^.!?\n\"]{0,40}\b(above|ahead of|first|top)\b[^.!?\n\"]{0,30}\b(all|every|other|others)\b",
    r"\bclaim that\b",
    r"\b(call|use|invoke)\s+(the\s+)?(save_job_or_event|get_student_preferences|search_jobs|rank_jobs|get_job_details|search_events)\b",
]
_INJECTION = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.IGNORECASE)
# A "sentence" stays inside one JSON string: stop at quotes, newlines, . ! ?
_SENTENCE = re.compile(r'[^."\n!?]*?(?:' + "|".join(INJECTION_PATTERNS) + r')[^."\n!?]*[.!?]?',
                       re.IGNORECASE)
REMOVED = "[removed: instruction-like text]"


def sanitize_untrusted(text: str):
    """Remove instruction-like sentences from retrieved data."""
    found = [m.group(0).strip() for m in _SENTENCE.finditer(text)]
    if not found:
        return text, []
    cleaned = _SENTENCE.sub(REMOVED, text)
    cleaned = re.sub(r"(?:\[removed: instruction-like text\]\s*)+", REMOVED + " ", cleaned)
    return cleaned, found


def wrap_untrusted(source: str, text: str) -> str:
    safe = text.replace("<", "&lt;").replace(">", "&gt;")
    return f'<untrusted_data source="{source}">{safe}</untrusted_data>'


# ---- G6: privacy and secrets -------------------------------------------------------------

SECRET_PATTERNS = [
    ("jwt", re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), "[REDACTED_TOKEN]"),
    ("bearer", re.compile(r"(?i)\bbearer\s+[\w\-.~+/=]{16,}"), "Bearer [REDACTED_TOKEN]"),
    ("bcrypt_hash", re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}"), "[REDACTED_HASH]"),
    ("aws_key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_KEY]"),
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_KEY]"),
    ("db_credentials", re.compile(r"(mongodb(?:\+srv)?|mysql(?:\+pymysql)?|postgres(?:ql)?)://[^:/\s@]+:[^@\s]+@"),
     r"\1://[REDACTED]@"),
    ("secret_field", re.compile(
        r'(?i)("?\b(password|passwd|password_hash|secret|secret_key|jwt_secret_key|api[_-]?key|access[_-]?token|aws_secret_access_key)\b"?\s*[:=]\s*)("[^"]*"|[^\s,}]+)'),
     r'\1"[REDACTED]"'),
]
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def redact(text: str, own_email: str | None = None, emails: bool = False):
    """-> (redacted text, list of what was redacted)."""
    kinds = []
    for kind, pattern, replacement in SECRET_PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n:
            kinds.append(kind)
    if emails:
        def keep_own(m):
            if own_email and m.group(0).lower() == own_email.lower():
                return m.group(0)
            kinds.append("email")
            return "[REDACTED_EMAIL]"
        text = EMAIL.sub(keep_own, text)
    return text, sorted(set(kinds))


# ---- G7: bounded execution -------------------------------------------------------------------

class Deadline:
    def __init__(self, seconds: float, clock=time.monotonic):
        self.clock, self.started, self.seconds = clock, clock(), seconds

    def remaining(self) -> float:
        return self.seconds - (self.clock() - self.started)

    def expired(self) -> bool:
        return self.remaining() <= 0


TOOL_ERROR = re.compile(r"^(Tool execution error|[A-Za-z ]+ error): ")


def is_recoverable_tool_error(result: str) -> bool:
    """An exception inside a tool (e.g. a database blip), not a business answer
    such as "No matching jobs were found." or a validation message."""
    return bool(TOOL_ERROR.match(result or ""))


# ---- G8: reliable answers --------------------------------------------------------------------

COMPANY = re.compile(r"Pair 15 Company \d{4}")
MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d{4,})(?:\.\d{1,2})?")
LISTING_HINT = re.compile(r"(?i)(\$\s?\d|deadline|internship at|company \d{4}|\bjob id\b)")


def grounding_check(answer: str, tool_texts: list[str]):
    """Flag company names or salaries in the answer that no tool returned."""
    evidence = "\n".join(tool_texts)
    numbers = {int(float(n)) for n in re.findall(r"\d+(?:\.\d+)?", evidence.replace(",", ""))}
    unknown_companies = sorted({c for c in COMPANY.findall(answer) if c not in evidence})
    unknown_amounts = []
    for m in MONEY.finditer(answer):
        value = int(m.group(1).replace(",", ""))
        if not any(abs(value - n) <= 1 for n in numbers):
            unknown_amounts.append(m.group(0))
    if not tool_texts and LISTING_HINT.search(answer):
        return event("G8", "grounding", "replaced",
                     "answer lists opportunities but no tool returned any data",
                     unverified=unknown_companies + unknown_amounts)
    if unknown_companies or unknown_amounts:
        return event("G8", "grounding", "flagged",
                     "answer contains values that no tool returned",
                     unverified=unknown_companies + unknown_amounts)
    return None


UNGROUNDED_REPLACEMENT = (
    "I can only list jobs, companies and events that come from the Handshake "
    "database, and I didn't look any up for this question, so I won't guess. "
    "Ask me again (for example \"search internships in Palo Alto\") and I will search.")
