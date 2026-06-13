import json
import os
from datetime import datetime, timezone
from config import LOG_FILE, LLM_MODEL

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
