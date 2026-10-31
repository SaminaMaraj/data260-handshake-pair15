"""Request tracing for all p15 services (Lab 2 Part 6).

Every request gets a trace_id:
  * taken from an incoming X-Trace-Id header (so a caller, the gateway or a
    Kafka consumer can continue a trace), otherwise newly generated
  * returned to the client as the X-Trace-Id response header
  * on every structured log line ({"trace_id": ..., "service": ..., ...})
  * copied into every Kafka message published during the request
    (events.make_event uses current_trace_id()), so the consumer's logs and
    database writes carry the same id

Stage timing. Each request collects spans; the assistant reports five stages:
  queue_wait_ms    waiting before the model starts (Ollama queue + network):
                   wall time of the model call minus Ollama's total_duration
  model_ms         model inference reported by Ollama (load + prompt + generation)
  db_ms            every MongoDB command, timed by a pymongo CommandListener
  tool_ms          tool execution excluding its database time
  other_ms         everything else (validation, guardrails, serialization)

Assistant requests (and memory-worker messages) are stored in the `traces`
collection, which scripts/trace_report.py analyses.
"""
import contextvars
import json
import sys
import time
import uuid
from dataclasses import dataclass, field

from pymongo import monitoring

TRACES = "traces"
_current: contextvars.ContextVar["Trace | None"] = contextvars.ContextVar("p15_trace", default=None)


@dataclass
class Trace:
    trace_id: str
    service: str
    name: str = ""
    started: float = field(default_factory=time.perf_counter)
    db_ms: float = 0.0
    db_ops: int = 0
    spans: list = field(default_factory=list)
    attributes: dict = field(default_factory=dict)

    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 1)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def start(service: str, name: str = "", trace_id: str | None = None) -> tuple[Trace, object]:
    trace = Trace(trace_id=_clean(trace_id) or new_trace_id(), service=service, name=name)
    return trace, _current.set(trace)


def finish(token) -> None:
    _current.reset(token)


def current() -> "Trace | None":
    return _current.get()


def current_trace_id() -> str | None:
    trace = _current.get()
    return trace.trace_id if trace else None


def _clean(value: str | None) -> str | None:
    """Accept a caller's id only if it looks like one (no log injection)."""
    if not value:
        return None
    value = value.strip()
    return value if 8 <= len(value) <= 64 and all(c.isalnum() or c in "-_" for c in value) else None


def add_span(stage: str, name: str, ms: float, **extra) -> None:
    trace = _current.get()
    if trace is not None:
        trace.spans.append({"stage": stage, "name": name, "ms": round(ms, 1),
                            "at_ms": trace.elapsed_ms(), **extra})


def log(event: str, **fields) -> None:
    """One JSON line per event, always with service and trace_id when known."""
    trace = _current.get()
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event}
    if trace:
        record.update(service=trace.service, trace_id=trace.trace_id)
    record.update(fields)
    print(json.dumps(record, default=str), file=sys.stdout, flush=True)


# ---- MongoDB command timing ----------------------------------------------------------------

class MongoTimer(monitoring.CommandListener):
    """Adds each MongoDB command's duration to the current request's trace.

    pymongo calls these hooks synchronously on the thread that ran the
    command, so the context variable is the request that issued it.
    """

    def started(self, event):
        pass

    def succeeded(self, event):
        self._record(event)

    def failed(self, event):
        self._record(event)

    def _record(self, event):
        trace = _current.get()
        if trace is not None:
            trace.db_ms += event.duration_micros / 1000
            trace.db_ops += 1


MONGO_TIMER = MongoTimer()


# ---- persistence and analysis ----------------------------------------------------------------

def stage_breakdown(trace: Trace, total_ms: float) -> dict:
    """The five assistant stages from the spans (all in ms)."""
    model_wall = sum(s["ms"] for s in trace.spans if s["stage"] == "model")
    model_ms = sum(s.get("inference_ms", s["ms"]) for s in trace.spans if s["stage"] == "model")
    tool_wall = sum(s["ms"] for s in trace.spans if s["stage"] == "tool")
    tool_db = sum(s.get("db_ms", 0.0) for s in trace.spans if s["stage"] == "tool")
    queue = max(0.0, model_wall - model_ms)
    tool_only = max(0.0, tool_wall - tool_db)
    db = trace.db_ms
    other = max(0.0, total_ms - model_wall - tool_only - db)
    return {"queue_wait_ms": round(queue, 1), "model_ms": round(model_ms, 1),
            "db_ms": round(db, 1), "tool_ms": round(tool_only, 1),
            "other_ms": round(other, 1), "total_ms": round(total_ms, 1)}


def save(db, trace: Trace, *, status: str, http_status: int | None = None,
         error: str | None = None, total_ms: float | None = None) -> dict:
    total_ms = trace.elapsed_ms() if total_ms is None else total_ms
    stages = stage_breakdown(trace, total_ms)
    doc = {"_id": f"{trace.trace_id}:{trace.service}:{trace.name}", "trace_id": trace.trace_id,
           "service": trace.service, "name": trace.name, "status": status,
           "http_status": http_status, "error": error, "stages": stages,
           "db_ops": trace.db_ops, "spans": trace.spans, "attributes": trace.attributes,
           "at": time.time()}
    try:
        db[TRACES].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    except Exception:
        pass  # tracing must never break the request
    return doc
