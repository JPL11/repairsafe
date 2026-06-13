import json
import os
from collections import Counter
from datetime import datetime, timezone
from config import LOG_FILE, LLM_MODEL, SUMMARY_FILE, SUMMARY_EVERY

# Truncation limits — see specs/auditor-spec.md for the reasoning.
_QUESTION_LIMIT = 300
_PREVIEW_LIMIT = 200
_CONSOLE_QUESTION_LIMIT = 60


def _utc_timestamp() -> str:
    """ISO 8601 UTC with a trailing Z, e.g. 2026-06-13T18:22:01.123456Z."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_interaction(question: str, tier: str, response: str, reason: str = "") -> None:
    """
    Append a structured record of this interaction to the audit log.

    Writes one JSON object per line (.jsonl) to LOG_FILE. Each record carries the
    four required fields (timestamp, tier, question, response_preview) plus three
    that make a log of 10,000 entries actually diagnosable: the classifier's
    reason, the full response length, and the model id.

    The question is truncated to 300 chars and the response preview to 200 chars.
    The logs/ directory is created if it doesn't exist. A one-line summary is
    printed to the terminal after each write.

    `reason` is optional so the documented (question, tier, response) contract
    still works; the app threads the classifier's reason through when it has one.
    """
    record = {
        "timestamp": _utc_timestamp(),
        "tier": tier,
        "question": question[:_QUESTION_LIMIT],
        "response_preview": response[:_PREVIEW_LIMIT],
        "reason": reason,
        "response_length": len(response),
        "model": LLM_MODEL,
    }

    # Create logs/ on first run (or after a cleanup) — .gitkeep is not a runtime
    # guarantee. exist_ok makes this idempotent and cheap on every call.
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # Append one line. ensure_ascii=False keeps unicode (arrows, accents) readable;
    # the explicit "\n" is what makes this JSONL rather than pretty-printed JSON.
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Real-time one-line terminal summary.
    q = question.replace("\n", " ")
    if len(q) > _CONSOLE_QUESTION_LIMIT:
        q = q[: _CONSOLE_QUESTION_LIMIT - 1] + "…"
    print(f'[LOGGED] tier={tier} | "{q}" → {len(response)} chars')

    # Optional challenge 3: roll up a session summary every Nth interaction.
    _maybe_write_session_summary()


def _read_log_records() -> list[dict]:
    """Parse every record currently in the audit log (skips any corrupt line)."""
    if not os.path.exists(LOG_FILE):
        return []
    records = []
    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # one bad line never breaks the rollup — that's the point of JSONL
    return records


def _maybe_write_session_summary() -> None:
    """
    After every SUMMARY_EVERY interactions, append an aggregate snapshot to
    SUMMARY_FILE: total interactions, the tier distribution, and the 3 most
    recent questions. Computed by reading and re-parsing the audit log, so it
    needs no in-memory state and survives restarts.
    """
    records = _read_log_records()
    total = len(records)
    if total == 0 or total % SUMMARY_EVERY != 0:
        return

    distribution = dict(Counter(r.get("tier", "unknown") for r in records))
    recent = [r.get("question", "") for r in records[-3:]]
    summary = {
        "timestamp": _utc_timestamp(),
        "total_interactions": total,
        "tier_distribution": distribution,
        "recent_questions": recent,
    }

    summary_dir = os.path.dirname(SUMMARY_FILE)
    if summary_dir:
        os.makedirs(summary_dir, exist_ok=True)
    with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    print(f"[SUMMARY] {total} interactions logged | distribution={distribution}")
