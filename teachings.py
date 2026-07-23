"""
Teaching-mode storage: a guided Q&A session whose answers get saved to a JSON
file on disk (next to the app) and injected into EmesGPT's system prompt on
every future request — a lightweight, permanent "extra layer" of personal
context on top of the static knowledge modules in knowledge.py.

This file intentionally has zero Flask/network dependencies so it's easy to
reason about and test on its own.
"""

import json
import os
import threading
from datetime import datetime, timezone

from runtime_paths import get_base_dir

# get_base_dir(), not this file's own folder: when packaged into a .exe with
# PyInstaller, this module's __file__ lives inside the temporary extraction
# dir (sys._MEIPASS), which is wiped on exit. teachings.json needs to persist
# next to the .exe itself, not vanish every time the app closes.
TEACHINGS_FILE = os.path.join(get_base_dir(), "teachings.json")

# RLock (not Lock): save_answer/delete_answer hold the lock while calling
# load_teachings(), which also acquires it — a plain Lock would deadlock.
_lock = threading.RLock()

# Prewritten starter questions. Users can answer these, skip them, or add
# their own custom questions through the wizard; AI-generated follow-ups
# get appended to this same list with source="ai-generated" when accepted.
PREWRITTEN_QUESTIONS = [
    {
        "id": "mission",
        "text": "What's the central mission behind EmesGPT, in your own words — what should it be fighting for?",
    },
    {
        "id": "relationship-with-god",
        "text": "How would you describe your relationship with God in a paragraph — distant, wrestling, close, something else?",
    },
    {
        "id": "shaping-concept",
        "text": "What's a Torah concept, verse, or teaching that has most shaped how you see the world, and why?",
    },
    {
        "id": "suffering-lens",
        "text": "When EmesGPT encounters suffering or tragedy in a news story, what lens should it apply — what should it say, and what should it avoid saying?",
    },
    {
        "id": "skepticism-targets",
        "text": "Are there specific narratives, institutions, or movements you want EmesGPT to be especially skeptical of by default?",
    },
    {
        "id": "gentleness-boundaries",
        "text": "Is there a topic or kind of situation where you want EmesGPT to be especially careful, gentle, or slow to judge?",
    },
    {
        "id": "free-will-providence",
        "text": "How do you personally balance free will and divine providence? How should EmesGPT talk about that tension?",
    },
    {
        "id": "surprising-belief",
        "text": "What's a belief of yours that most people would find surprising, and how firmly should EmesGPT hold it?",
    },
    {
        "id": "fearless-vs-compassionate",
        "text": "EmesGPT is supposed to be fearless but never cruel — where's a line you've seen it get that balance wrong, or where should it lean more one way?",
    },
    {
        "id": "always-remember",
        "text": "Anything else you want EmesGPT to always keep in mind about your worldview, going forward?",
    },
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _empty_state():
    return {"entries": []}


def load_teachings():
    """Returns the full stored state: {"entries": [ {id, question, answer, source, updated_at}, ... ]}"""
    with _lock:
        if not os.path.exists(TEACHINGS_FILE):
            return _empty_state()
        try:
            with open(TEACHINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return _empty_state()
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            return _empty_state()
        return data


def _write_teachings(data):
    tmp_path = TEACHINGS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, TEACHINGS_FILE)  # atomic on POSIX and Windows


def save_answer(question_id: str, question_text: str, answer_text: str, source: str = "prewritten"):
    """Create or update one Q&A entry, keyed by question_id."""
    question_text = (question_text or "").strip()
    answer_text = (answer_text or "").strip()
    if not question_id or not question_text:
        raise ValueError("question_id and question_text are required")

    with _lock:
        data = load_teachings()
        entries = data["entries"]
        existing = next((e for e in entries if e.get("id") == question_id), None)
        if existing:
            existing["question"] = question_text
            existing["answer"] = answer_text
            existing["source"] = source
            existing["updated_at"] = _now_iso()
        else:
            entries.append(
                {
                    "id": question_id,
                    "question": question_text,
                    "answer": answer_text,
                    "source": source,
                    "updated_at": _now_iso(),
                }
            )
        _write_teachings(data)
        return data


def delete_answer(question_id: str):
    with _lock:
        data = load_teachings()
        data["entries"] = [e for e in data["entries"] if e.get("id") != question_id]
        _write_teachings(data)
        return data


def reset_teachings():
    with _lock:
        data = _empty_state()
        _write_teachings(data)
        return data


def build_teachings_block():
    """Render saved answers (with non-empty text) for injection into the
    system prompt. Returns "" if nothing has been taught yet."""
    data = load_teachings()
    answered = [e for e in data["entries"] if (e.get("answer") or "").strip()]
    if not answered:
        return ""

    parts = [
        "### Personal Teachings (from a guided session with the user — treat as "
        "authoritative first-person context about who they are and what they believe)"
    ]
    for entry in answered:
        parts.append(f"Q: {entry['question']}\nA: {entry['answer']}")
    return "\n\n".join(parts)
