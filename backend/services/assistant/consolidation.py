"""Memory consolidation and extraction (Lab 2 Part 3).

consolidate(entries, client) turns one student's learned memory into a
shorter, consistent list. The work is split so the model does only the part
that needs language understanding:

  1. Code merges exact duplicates (same category and text, ignoring case,
     spacing and punctuation). Certain and free.
  2. Code splits the rest BY CATEGORY (location, preference, education, ...)
     and sends each category to the model separately: small inputs, short
     answers, far fewer mistakes than one 60-entry request.
  3. The model only CLUSTERS: it returns groups of entry numbers that are
     about the same single fact, labelled "duplicate" or "contradiction".
     It does not rewrite entries, so it cannot paraphrase or invent facts.
  4. Code validates the answer (JSON shape, entry numbers exist) and applies
     ONE policy to every group: the newest entry wins, with the newest date.
     For a contradiction that keeps the current fact; for duplicates it keeps
     the latest wording. An entry listed in two groups joins those groups
     (logged as a correction). Invalid answers get ONE re-prompt with the
     specific errors; if that also fails, that category alone falls back to
     the deterministic near-duplicate merge.

Every step is recorded in `decisions`/`corrections`/`errors`, so the report
can show what was merged, what was resolved and where the model was wrong.

extract(conversation, client) is the session-end step: it asks the model
for lasting facts the student stated about themselves.

History: version 1 asked the model to rewrite the whole memory as JSON in one
call. qwen3:8b either took minutes per call (thinking on) or double-counted
entries and was rejected (thinking off). See docs/MEMORY.md.
"""
import json
import re
import string
import time

from services.common import tracing

from services.assistant.memory import CATEGORIES, MAX_DESCRIPTION, normalize_category

MAX_AFTER = 40          # the handout's target: below 40 entries (checked by the report)
MAX_MODEL_ATTEMPTS = 2  # per category: first answer + one re-prompt with the errors


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


# ---- step 2: the model clusters one category at a time ------------------------------

GROUP_PROMPT = """You help a career assistant tidy what it remembers about ONE student.

Below are memory entries in the category "{category}", one per line, as
"[number] YYYY-MM-DD | description".

Find groups of entries that are about the SAME single fact:
- "duplicate": they say the same thing in different words.
- "contradiction": same fact, but they disagree (e.g. "lives in Austin" and
  later "moved to Denver"; "wants part-time work" and later "now wants
  full-time work"; a number that changed).
Do NOT group entries about different facts, even if related: "lives in Austin"
and "wants to stay in Texas" are different facts; "knows Java" and "prefers
Java over C++" are different facts.

Return JSON only:
{{"groups": [{{"ids": [numbers], "type": "duplicate" or "contradiction", "reason": "under 12 words"}}]}}
Each number may appear in at most one group. Only list groups with 2 or more
entries; entries you leave out are kept unchanged. Return {{"groups": []}} if
nothing belongs together.
"""


def _category_messages(category: str, rows: list[dict]) -> list[dict]:
    lines = "\n".join(f"[{n}] {r['date']} | {r['description']}"
                       for n, r in enumerate(rows, start=1))
    return [{"role": "system", "content": GROUP_PROMPT.format(category=category)},
            {"role": "user", "content": f"Entries ({len(rows)}):\n{lines}"}]


def validate_groups(reply: str, count: int):
    """-> (groups, corrections, errors). errors means re-prompt.

    groups: [{ids (1-based, sorted), type, reason}], no id in two groups.
    """
    try:
        data = json.loads(reply)
        items = data["groups"]
        assert isinstance(items, list)
    except (ValueError, KeyError, TypeError, AssertionError):
        return None, [], ['The reply was not JSON of the form {"groups": [...]}.']

    errors, clean = [], []
    for n, item in enumerate(items, start=1):
        ids = item.get("ids") if isinstance(item, dict) else None
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            errors.append(f"Group {n} needs an \"ids\" list of entry numbers.")
            continue
        unknown = sorted({i for i in ids if not 1 <= i <= count})
        if unknown:
            errors.append(f"Group {n} uses entry numbers that do not exist: {unknown} "
                          f"(valid: 1 to {count}).")
            continue
        ids = sorted(set(ids))
        if len(ids) < 2:
            continue  # a group of one changes nothing
        kind = item.get("type") if item.get("type") in ("duplicate", "contradiction") else "duplicate"
        clean.append({"ids": ids, "type": kind, "reason": str(item.get("reason") or "")[:200]})
    if errors:
        return None, [], errors

    # An entry in two groups means those groups describe one fact: join them.
    joined, corrections = [], []
    for group in clean:
        overlapping = [g for g in joined if set(g["ids"]) & set(group["ids"])]
        if not overlapping:
            joined.append(dict(group))
            continue
        target = overlapping[0]
        for other in overlapping[1:]:
            target["ids"] = sorted(set(target["ids"]) | set(other["ids"]))
            target["type"] = "contradiction" if "contradiction" in (target["type"], other["type"]) else target["type"]
            joined.remove(other)
        shared = sorted(set(target["ids"]) & set(group["ids"]))
        target["ids"] = sorted(set(target["ids"]) | set(group["ids"]))
        if group["type"] == "contradiction":
            target["type"] = "contradiction"
        target["reason"] = target["reason"] or group["reason"]
        corrections.append(f"entries {shared} were listed in more than one group; "
                           f"the groups were joined into {target['ids']}")
    return joined, corrections, []


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

def _line(e: dict) -> str:
    return f"{e['date']} | {e['category']} | {e['description']}"


def consolidate(entries: list[dict], client) -> dict:
    """entries: [{id, date, category, description}] (ids are local numbers).

    Returns {entries, decisions, corrections, method, model_attempts,
    model_calls, errors, fallback_categories}.
    """
    entries = [{**e, "category": normalize_category(e["category"])} for e in entries]
    rows, decisions = merge_exact_duplicates(entries)

    by_category: dict[str, list[dict]] = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row)

    final, corrections, errors, fallback = [], [], [], []
    model_calls = max_attempts = 0
    for category, group_rows in by_category.items():
        if len(group_rows) < 2:
            final += [{**r, "action": "kept", "reason": "only entry in its category"}
                      for r in group_rows]
            continue
        messages = _category_messages(category, group_rows)
        groups = None
        for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
            reply = _ask_model(client, messages)
            model_calls += 1
            max_attempts = max(max_attempts, attempt)
            groups, fixes, problems = validate_groups(reply, len(group_rows))
            if not problems:
                corrections += [f"{category}: {c}" for c in fixes]
                break
            errors.append({"attempt": attempt, "category": category, "errors": problems})
            groups = None
            messages = messages + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": "Your answer broke these rules:\n- "
                 + "\n- ".join(problems) + "\nReturn the corrected JSON only."}]

        if groups is None:  # this category only: deterministic merge
            fallback.append(category)
            kept, more = deterministic(group_rows)
            final += kept
            decisions += [{**d, "category": category} for d in more]
            continue

        grouped = set()
        for g in groups:
            members = [group_rows[i - 1] for i in g["ids"]]
            grouped |= set(g["ids"])
            newest = max(members, key=lambda r: (r["date"], r["id"]))
            sources = sorted(x for r in members for x in r["sources"])
            action = "resolved" if g["type"] == "contradiction" else "merged"
            kept = {"date": newest["date"], "category": category,
                    "description": newest["description"], "sources": sources,
                    "action": action, "reason": g["reason"]}
            final.append(kept)
            decisions.append({"step": "model", "action": action, "category": category,
                              "sources": sources, "kept": _line(kept),
                              "reason": (g["reason"] + "; " if g["reason"] else "")
                                        + "newest entry kept"})
        final += [{**r, "action": "kept", "reason": "no related entry"}
                  for n, r in enumerate(group_rows, start=1) if n not in grouped]

    final = [{k: e[k] for k in ("date", "category", "description", "sources", "action", "reason")}
             for e in sorted(final, key=lambda e: (e["date"], e["category"], e["description"]))]
    if not model_calls:
        method = "no_model_needed"
    elif not fallback:
        method = "model"
    elif len(fallback) == sum(len(v) > 1 for v in by_category.values()):
        method = "deterministic_fallback"
    else:
        method = "model+fallback(" + ",".join(fallback) + ")"
    return {"entries": final, "decisions": decisions, "corrections": corrections,
            "method": method, "model_attempts": max_attempts, "model_calls": model_calls,
            "errors": errors, "fallback_categories": fallback}


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
