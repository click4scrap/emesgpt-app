"""
First-prompt log: a lightweight, append-only record of just the opening
message of every new conversation started against /api/chat, stored as JSON
on disk next to the app (same pattern as teachings.py).

Deliberately NOT the full conversation — just the first line someone typed
when they opened a fresh chat. That's enough to see what real visitors are
actually asking about at a glance, without storing entire transcripts.

Capped at MAX_ENTRIES so the file can't grow without bound on a long-running
server; oldest entries are dropped first once the cap is hit.
"""

import json
import os
import threading
from datetime import datetime, timezone

from runtime_paths import get_base_dir

PROMPT_LOG_FILE = os.path.join(get_base_dir(), "prompt_log.json")

MAX_ENTRIES = 1000

_lock = threading.Lock()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load():
    with _lock:
        if not os.path.exists(PROMPT_LOG_FILE):
            return []
        try:
            with open(PROMPT_LOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return data


def _write(entries):
    tmp_path = PROMPT_LOG_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, PROMPT_LOG_FILE)  # atomic on POSIX and Windows


def log_first_prompt(text: str):
    """Append one entry recording the opening message of a new
    conversation. No-ops on blank input so empty/whitespace-only messages
    (which never make it past validation anyway) don't clutter the log."""
    text = (text or "").strip()
    if not text:
        return

    with _lock:
        entries = _load()
        entries.append({"text": text, "at": _now_iso()})
        if len(entries) > MAX_ENTRIES:
            entries = entries[-MAX_ENTRIES:]
        _write(entries)


def load_first_prompts():
    """Returns all logged entries, oldest first: [{"text": ..., "at": ...}, ...]"""
    return _load()
