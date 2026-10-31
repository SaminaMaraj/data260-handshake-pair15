"""Memory consolidation and extraction (Lab 2 Part 3).

consolidate(entries, client) turns one student's learned memory into a
shorter, consistent list:

  1. Code merges exact duplicates (same category, same text ignoring case,
     spacing and punctuation). Certain and free.
  2. The model merges near-duplicates and resolves contradictions, answering
     in JSON where every output entry names the input entries it came from.
  3. Code validates that answer:
       - every input entry is used exactly once (nothing silently dropped,
         nothing counted twice)
       - sources exist (nothing invented)
       - the date is the newest date among its sources (a resolved
         contradiction keeps the newer fact)
       - valid category, non-empty description, fewer than MAX_AFTER entries
     Fixable problems (wrong date, unknown category) are corrected and logged;
     anything else gets ONE re-prompt with the specific errors, then the
     deterministic fallback.

Every step is recorded in `decisions`, so the report can show what was
merged, what was resolved and where the model was wrong.

extract(conversation, client) is the session-end step: it asks the model
for lasting facts the student stated about themselves and validates them
the same way.
"""
import json
import re
import string
import time

from services.common import tracing

from services.assistant.memory import CATEGORIES, MAX_DESCRIPTION, normalize_category

MAX_AFTER = 40          # the handout's target: below 40 entries
MAX_MODEL_ATTEMPTS = 2  # first answer + one re-prompt with the errors


class ModelUnavailable(RuntimeError):
    """The model could not be reached; the Kafka consumer retries this."""


# ---- helpers -------------------------------------------------------------------------

_PUNCT = str.maketrans("", "", string.punctuation)


def normalized(text: str) -> str:
    return " ".join(text.casefold().translate(_PUNCT).split())


def _tokens(text: str) -> set[str]:
    return set(normalized(text).split())


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    match = re.search(r"\{.*\}", text, re.S)
    return match.group(0) if match else text


def _ask_model(client, messages) -> str:
    started = time.perf_counter()
    reply = client.complete(messages=messages, tools=None, response_format="json")
    usage = getattr(client, "last_usage", None) or {}
    wall = (time.perf_counter() - started) * 1000
    tracing.add_span("model", "consolidation", wall,
                     inference_ms=usage.get("inference_ms") or round(wall, 1),
                     prompt_tokens=usage.get("prompt_tokens"),
                     completion_tokens=usage.get("completion_tokens"))
    content = reply.get("content") or ""
    if content.startswith("Ollama request failed"):
        raise ModelUnavailable(content)
    return _strip_thinking(content)


# ---- step 1: exact duplicates ---------------------------------------------------------

def merge_exact_duplicates(entries: list[dict]):
    """entries: [{id, date, category, description}] -> (kept, decisions)."""
    groups: dict[tuple, list[dict]] = {}
    for e in entries:
        groups.setdefault((e["category"], normalized(e["description"])), []).append(e)
    kept, decisions = [], []
    for group in groups.values():
        newest = max(group, key=lambda e: (e["date"], e["id"]))
        original = min(group, key=lambda e: (e["date"], e["id"]))
        merged = {**newest, "description": original["description"],
                  "sources": sorted(x for e in group for x in e.get("sources", [e["id"]]))}
        kept.append(merged)
        if len(group) > 1:
            decisions.append({
                "step": "code", "action": "merged_exact_duplicates",
                "sources": merged["sources"],
                "kept": f"{merged['date']} | {merged['category']} | {merged['description']}",
                "reason": f"{len(group)} entries with the same text (ignoring case and "
                          "punctuation); kept the newest date and the original wording"})
    kept.sort(key=lambda e: (e["date"], e["id"]))
    return kept, decisions


# ---- step 2: the model -----------------------------------------------------------------

CONSOLIDATE_PROMPT = """You consolidate what a career assistant remembers about ONE student.

Input: numbered memory entries, each "[number] YYYY-MM-DD | category | description".

Return JSON only, exactly this shape:
{{"entries": [{{"sources": [numbers], "date": "YYYY-MM-DD", "category": "...",
  "description": "...", "action": "kept" | "merged" | "resolved", "reason": "..."}}]}}

Rules:
1. Every input number must appear in the sources of exactly ONE output entry.
2. Entries that say the same thing in different words: ONE entry, action "merged".
3. Entries that contradict each other (same topic, incompatible facts, e.g. two
   different preferred cities, or "likes X" then "no longer likes X"): keep ONLY
   the fact from the NEWEST date, list all of them in sources, action "resolved",
   and say in reason which entry replaced which.
4. Entries about different things stay separate, action "kept".
5. date = the newest date among that entry's sources.
6. category must be one of: {categories}.
7. Use only facts in the input. Never invent or embellish. Keep each
   description under {max_desc} characters.
8. The output must have fewer than {max_after} entries.
"""


def _model_messages(entries: list[dict]) -> list[dict]:
    lines = "\n".join(f"[{e['id']}] {e['date']} | {e['category']} | {e['description']}"
                      for e in entries)
    system = CONSOLIDATE_PROMPT.format(categories=", ".join(CATEGORIES),
                                       max_desc=MAX_DESCRIPTION, max_after=MAX_AFTER)
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"Memory entries ({len(entries)}):\n{lines}"}]


def validate(model_json: str, entries: list[dict]):
    """-> (clean_entries, corrections, errors). errors means re-prompt."""
    by_id = {e["id"]: e for e in entries}
    errors, corrections = [], []
    try:
        data = json.loads(model_json)
        items = data["entries"]
        assert isinstance(items, list)
    except (ValueError, KeyError, TypeError, AssertionError):
        return None, [], ["The reply was not JSON of the form {\"entries\": [...]}."]

    used: dict[int, int] = {}
    clean = []
    for n, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"Output entry {n} is not an object.")
            continue
        sources = item.get("sources")
        if not isinstance(sources, list) or not sources or \
                not all(isinstance(s, int) for s in sources):
            errors.append(f"Output entry {n} needs a non-empty list of integer sources.")
            continue
        unknown = [s for s in sources if s not in by_id]
        if unknown:
            errors.append(f"Output entry {n} cites sources that do not exist: {unknown}.")
            continue
        for s in sources:
            used[s] = used.get(s, 0) + 1
        description = " ".join(str(item.get("description") or "").split())
        if not description:
            errors.append(f"Output entry {n} has an empty description.")
            continue
        if len(description) > MAX_DESCRIPTION:
            description = description[:MAX_DESCRIPTION]
            corrections.append(f"entry {n}: description shortened to {MAX_DESCRIPTION} chars")
        newest = max(by_id[s]["date"] for s in sources)
        if item.get("date") != newest:
            corrections.append(f"entry {n} (sources {sources}): model date "
                               f"{item.get('date')!r} corrected to newest source date {newest}")
        category = str(item.get("category") or "").strip().lower()
        if category not in CATEGORIES:
            fixed = by_id[max(sources, key=lambda s: by_id[s]['date'])]["category"]
            corrections.append(f"entry {n}: category {category!r} is not valid; "
                               f"used {fixed!r} from its newest source")
            category = fixed
        clean.append({"date": newest, "category": category, "description": description,
                      "sources": sorted(sources), "action": item.get("action") or "kept",
                      "reason": str(item.get("reason") or "")[:300]})

    missing = sorted(set(by_id) - set(used))
    twice = sorted(s for s, n in used.items() if n > 1)
    if missing:
        errors.append(f"These input entries are not in any output entry: {missing}. "
                      "Each one must be kept, merged or resolved.")
    if twice:
        errors.append(f"These input entries appear in more than one output entry: {twice}.")
    if len(clean) >= MAX_AFTER:
        errors.append(f"The output has {len(clean)} entries; it must have fewer than {MAX_AFTER}.")
    return clean, corrections, errors


# ---- step 3: deterministic fallback ------------------------------------------------------

def deterministic(entries: list[dict]):
    """No model: merge near-duplicates (>= 0.75 word overlap, same category).
    Contradictions cannot be detected reliably without the model, so they are
    left in place and flagged in the decisions."""
    kept, decisions = [], []
    for e in sorted(entries, key=lambda x: (x["date"], x["id"])):
        match = next((k for k in kept if k["category"] == e["category"]
                      and similarity(k["description"], e["description"]) >= 0.75), None)
        if match is None:
            kept.append({**e, "sources": list(e.get("sources", [e["id"]])),
                         "action": "kept", "reason": "fallback: no near-duplicate"})
        else:
            match["sources"] += e.get("sources", [e["id"]])
            match.update(date=e["date"], description=e["description"], action="merged",
                         reason="fallback: >= 75% word overlap; kept newer wording")
            decisions.append({"step": "fallback", "action": "merged_near_duplicates",
                              "sources": sorted(match["sources"]), "reason": match["reason"]})
    return kept, decisions


# ---- public entry points ----------------------------------------------------------------------

def consolidate(entries: list[dict], client) -> dict:
    """entries: [{id, date, category, description}] (ids are local numbers).

    Returns {entries, decisions, corrections, method, model_attempts, errors}.
    """
    entries = [{**e, "category": normalize_category(e["category"])} for e in entries]
    stage1, decisions = merge_exact_duplicates(entries)
    # Renumber the merged rows so the model sees one number per row.
    for n, row in enumerate(stage1, start=1):
        row["id"], row["original_sources"] = n, row.pop("sources")
    corrections, all_errors = [], []
    messages = _model_messages(stage1)

    for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
        reply = _ask_model(client, messages)
        clean, fixes, errors = validate(reply, stage1)
        if not errors:
            corrections += fixes
            originals = {row["id"]: row["original_sources"] for row in stage1}
            final = []
            for item in clean:
                srcs = sorted(x for s in item["sources"] for x in originals[s])
                final.append({**item, "sources": srcs})
                if item["action"] in ("merged", "resolved") or len(srcs) > 1:
                    decisions.append({"step": "model", "action": item["action"],
                                      "sources": srcs,
                                      "kept": f"{item['date']} | {item['category']} | "
                                              f"{item['description']}",
                                      "reason": item["reason"]})
            return {"entries": final, "decisions": decisions, "corrections": corrections,
                    "method": "model", "model_attempts": attempt, "errors": all_errors}
        all_errors.append({"attempt": attempt, "errors": errors})
        messages = messages + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "Your answer broke these rules:\n- "
             + "\n- ".join(errors) + "\nReturn the corrected JSON only."}]

    fallback, more = deterministic([{**row, "sources": row["original_sources"]}
                                    for row in stage1])
    return {"entries": fallback, "decisions": decisions + more, "corrections": corrections,
            "method": "deterministic_fallback", "model_attempts": MAX_MODEL_ATTEMPTS,
            "errors": all_errors}


EXTRACT_PROMPT = """Read a conversation between a student and a career assistant.
List lasting facts the STUDENT stated about THEMSELVES that would help in future
sessions: preferences, location, skills, goals, availability, constraints.
Ignore job or event listings the assistant showed, one-off requests, and
anything about other people. At most 5 facts.

Return JSON only: {{"entries": [{{"category": "...", "description": "..."}}]}}
category is one of: {categories}. Return {{"entries": []}} if there is nothing lasting.
"""


def extract(conversation: list[dict], client) -> list[dict]:
    """Session end: lasting facts the student stated -> [{category, description}]."""
    said = [m.get("content", "") for m in conversation
            if m.get("role") == "user" and not str(m.get("content", "")).startswith(
                ("/memory", "[Assistant loop correction]"))]
    if not said:
        return []
    messages = [{"role": "system", "content": EXTRACT_PROMPT.format(
                    categories=", ".join(CATEGORIES))},
                {"role": "user", "content": "Student messages:\n- " + "\n- ".join(said)}]
    try:
        items = json.loads(_ask_model(client, messages)).get("entries", [])
    except (ValueError, AttributeError):
        return []
    facts = []
    for item in items[:5] if isinstance(items, list) else []:
        if isinstance(item, dict) and str(item.get("description") or "").strip():
            facts.append({"category": normalize_category(str(item.get("category"))),
                          "description": " ".join(str(item["description"]).split())
                          [:MAX_DESCRIPTION]})
    return facts
