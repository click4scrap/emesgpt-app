import os
import re
import threading
import time

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
# redeploy
from knowledge import SYSTEM_PROMPT, build_context_block
import teachings as teachings_store
from runtime_paths import get_base_dir

# Explicit path, not just load_dotenv()'s default cwd-search: when packaged
# into a .exe, the working directory a user's double-click launches with
# isn't guaranteed, so we point straight at the .env expected next to the
# app/exe instead of hoping cwd lines up.
load_dotenv(os.path.join(get_base_dir(), ".env"))

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = os.environ.get("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Soft guardrails on input size. Matches the client-side limits in index.html.
# Not real token counts, just sane ceilings to keep requests/cost bounded.
MAX_INPUT_CHARS = int(os.environ.get("MAX_INPUT_CHARS", 50000))
MAX_CONVERSATION_CHARS = int(os.environ.get("MAX_CONVERSATION_CHARS", 150000))

# Hard cap on Groq calls (via /api/chat + /api/analyze) for this run of
# the server. Deliberately in-memory, not written to disk: it's meant to
# reset whenever the server restarts, and a "Reset" button in the UI can
# also zero it out early. This is a global counter shared by every browser
# tab/conversation talking to this server, not a per-conversation limit.
MESSAGE_LIMIT = int(os.environ.get("MESSAGE_LIMIT", 10))
_usage_lock = threading.Lock()
_message_count = 0


def get_usage():
    with _usage_lock:
        return {
            "used": _message_count,
            "limit": MESSAGE_LIMIT,
            "remaining": max(0, MESSAGE_LIMIT - _message_count),
        }


def usage_limit_reached():
    with _usage_lock:
        return _message_count >= MESSAGE_LIMIT


def increment_usage():
    global _message_count
    with _usage_lock:
        _message_count += 1
        return {
            "used": _message_count,
            "limit": MESSAGE_LIMIT,
            "remaining": max(0, MESSAGE_LIMIT - _message_count),
        }


def reset_usage():
    global _message_count
    with _usage_lock:
        _message_count = 0
        return {"used": 0, "limit": MESSAGE_LIMIT, "remaining": MESSAGE_LIMIT}


def limit_reached_response():
    return (
        {
            "error": (
                f"You've reached the {MESSAGE_LIMIT}-message limit for this session. "
                "Click Reset to keep going, or restart the server."
            ),
            "limit_reached": True,
            "usage": get_usage(),
        },
        429,
    )


def build_system_content():
    """Rebuilt on every call (cheap: string concat + one small file read) so
    that answers saved through the teaching wizard take effect immediately,
    with no server restart needed."""
    parts = [SYSTEM_PROMPT]
    parts.append(
        "\n\n--- BACKGROUND WISDOM (use as a moral lens, not proof texts; "
        "cite only when genuinely relevant) ---\n\n" + build_context_block()
    )
    teachings_block = teachings_store.build_teachings_block()
    if teachings_block:
        parts.append("\n\n" + teachings_block)
    return "".join(parts)

YOUTUBE_ID_PATTERNS = [
    r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
    r"youtu\.be\/([0-9A-Za-z_-]{11})",
]


def extract_video_id(url: str):
    for pattern in YOUTUBE_ID_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


YOUTUBE_URL_ONLY = re.compile(
    r"^https?:\/\/(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)[0-9A-Za-z_-]{11}\S*$"
)


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_URL_ONLY.match(text.strip()))


def fetch_transcript_text(url: str):
    """Returns (transcript_text, error_message). Exactly one is None."""
    video_id = extract_video_id(url)
    if not video_id:
        return None, "Couldn't find a video ID in that URL."
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
    except TranscriptsDisabled:
        return None, "Captions are disabled for this video. Paste the transcript manually (e.g. via DownSub)."
    except NoTranscriptFound:
        return None, "No transcript found for this video. Paste the transcript manually."
    except VideoUnavailable:
        return None, "That video is unavailable."
    except Exception as exc:  # noqa: BLE001 - surface any other extraction failure to the user
        return None, f"Couldn't fetch transcript: {exc}"
    return " ".join(chunk["text"] for chunk in transcript_list), None


def resolve_user_text(text: str):
    """Apply the char cap + YouTube auto-fetch to a single piece of user text.

    Returns (resolved_text, source_note, error_response_tuple). Exactly one
    of (resolved_text, error_response_tuple) is set; source_note may be None.
    """
    text = (text or "").strip()
    if not text:
        return None, None, ({"error": "Paste an article, transcript, or YouTube link to analyze."}, 400)

    if is_youtube_url(text):
        transcript, error = fetch_transcript_text(text)
        if error:
            return None, None, ({"error": error}, 422)
        if len(transcript) > MAX_INPUT_CHARS:
            return None, None, (
                {
                    "error": (
                        f"That video's transcript is {len(transcript):,} characters — longer than the "
                        f"{MAX_INPUT_CHARS:,} char limit. Trim it and paste manually instead."
                    )
                },
                413,
            )
        return transcript, "(Transcript auto-extracted from YouTube link.)", None

    if len(text) > MAX_INPUT_CHARS:
        return None, None, (
            {"error": f"That's {len(text):,} characters — trim it below {MAX_INPUT_CHARS:,} and try again."},
            413,
        )

    return text, None, None


def call_groq(messages: list):
    """messages already includes the system message. Returns (content, error_response_tuple)."""
    if not GROQ_API_KEY:
        return None, ({"error": "GROQ_API_KEY is not set on the server. See README for setup."}, 500)

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
    }

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        return None, ({"error": f"Groq API error ({resp.status_code}): {resp.text[:500]}"}, 502)
    except requests.exceptions.RequestException as exc:
        return None, ({"error": f"Couldn't reach Groq API: {exc}"}, 502)

    result = resp.json()
    try:
        return result["choices"][0]["message"]["content"], None
    except (KeyError, IndexError):
        return None, ({"error": "Unexpected response shape from Groq."}, 502)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/teach")
def teach_page():
    return render_template("teach.html")


@app.route("/api/teach/questions", methods=["GET"])
def teach_questions():
    """Prewritten questions merged with whatever's already been answered
    (including any custom / AI-generated questions from past sessions), so
    reopening the wizard resumes where you left off."""
    data = teachings_store.load_teachings()
    answered_by_id = {e["id"]: e for e in data["entries"]}

    questions = []
    for q in teachings_store.PREWRITTEN_QUESTIONS:
        entry = answered_by_id.pop(q["id"], None)
        questions.append(
            {
                "id": q["id"],
                "text": q["text"],
                "answer": entry["answer"] if entry else "",
                "source": "prewritten",
            }
        )
    # Any remaining entries are custom/AI-generated questions from earlier sessions.
    for entry in answered_by_id.values():
        questions.append(
            {
                "id": entry["id"],
                "text": entry["question"],
                "answer": entry["answer"],
                "source": entry.get("source", "custom"),
            }
        )
    return jsonify({"questions": questions})


@app.route("/api/teach/save", methods=["POST"])
def teach_save():
    data = request.get_json(force=True) or {}
    question_id = (data.get("id") or "").strip()
    question_text = (data.get("question") or "").strip()
    answer_text = (data.get("answer") or "").strip()
    source = (data.get("source") or "custom").strip()

    if not question_id:
        # Custom question with no id yet — derive a stable-ish one.
        slug = re.sub(r"[^a-z0-9]+", "-", question_text.lower()).strip("-")[:40]
        question_id = f"custom-{slug or 'question'}-{int(time.time())}"

    if not question_text:
        return jsonify({"error": "Missing question text."}), 400

    updated = teachings_store.save_answer(question_id, question_text, answer_text, source=source)
    return jsonify({"id": question_id, "entries": updated["entries"]})


@app.route("/api/teach/reset", methods=["POST"])
def teach_reset():
    data = teachings_store.reset_teachings()
    return jsonify(data)


@app.route("/api/teach/suggest-followup", methods=["POST"])
def teach_suggest_followup():
    """Optional AI-generated follow-up question based on the most recent
    answer. Purely a convenience — the wizard works fine without it.

    Deliberately NOT subject to MESSAGE_LIMIT: teaching is a one-time setup
    session and shouldn't get cut off mid-conversation. Only /api/chat and
    /api/analyze (the main chat interface) are capped."""
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    if not answer:
        return jsonify({"error": "Answer the current question first."}), 400

    prompt_messages = [
        {
            "role": "system",
            "content": (
                "You are helping build a personal knowledge base for a Torah-rooted "
                "AI assistant called EmesGPT. Given the user's last question and answer, "
                "propose exactly ONE thoughtful follow-up question that would deepen the "
                "assistant's understanding of the user's worldview or beliefs. "
                "Reply with ONLY the question itself — no preamble, no quotes, no numbering."
            ),
        },
        {"role": "user", "content": f"Question: {question}\nAnswer: {answer}"},
    ]
    suggestion, err = call_groq(prompt_messages)
    if err:
        body, status = err
        return jsonify(body), status

    return jsonify({"question": suggestion.strip()})


@app.route("/api/usage", methods=["GET"])
def usage():
    return jsonify(get_usage())


@app.route("/api/usage/reset", methods=["POST"])
def usage_reset():
    return jsonify(reset_usage())


@app.route("/api/youtube-transcript", methods=["POST"])
def youtube_transcript():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Paste a YouTube URL first."}), 400

    text, error = fetch_transcript_text(url)
    if error:
        return jsonify({"error": error}), 422
    return jsonify({"transcript": text})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """One-shot analysis (no conversation memory). Kept for backward compat /
    scripted single-call use; the UI now uses /api/chat instead."""
    data = request.get_json(force=True) or {}
    text, source_note, err = resolve_user_text(data.get("text"))
    if err:
        body, status = err
        return jsonify(body), status

    if usage_limit_reached():
        body, status = limit_reached_response()
        return jsonify(body), status

    analysis, err = call_groq(
        [
            {"role": "system", "content": build_system_content()},
            {"role": "user", "content": text},
        ]
    )
    if err:
        body, status = err
        return jsonify(body), status

    usage_now = increment_usage()
    return jsonify({"analysis": analysis, "source_note": source_note, "usage": usage_now})


@app.route("/api/chat", methods=["POST"])
def chat():
    """Conversational endpoint. The client sends the full running history
    (list of {role: 'user'|'assistant', content}); the server prepends the
    system prompt + knowledge base and forwards everything to Groq so it
    has full context, same as talking to Groq directly."""
    data = request.get_json(force=True) or {}
    history = data.get("messages")

    if not isinstance(history, list) or not history:
        return jsonify({"error": "No conversation history provided."}), 400

    last = history[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        return jsonify({"error": "The last message in the conversation must be from the user."}), 400

    for msg in history:
        if not isinstance(msg, dict) or msg.get("role") not in ("user", "assistant") or "content" not in msg:
            return jsonify({"error": "Malformed message in conversation history."}), 400

    resolved_text, source_note, err = resolve_user_text(last.get("content"))
    if err:
        body, status = err
        return jsonify(body), status

    # Only the outgoing copy sent to Groq gets the YouTube link swapped
    # for its transcript — the client keeps the original link in its own
    # copy of the history, so the chat log still shows what the user typed.
    outgoing = history[:-1] + [{"role": "user", "content": resolved_text}]

    total_chars = sum(len(m.get("content", "")) for m in outgoing)
    if total_chars > MAX_CONVERSATION_CHARS:
        return jsonify(
            {
                "error": (
                    f"This conversation has grown to {total_chars:,} characters, past the "
                    f"{MAX_CONVERSATION_CHARS:,} char limit. Start a new conversation to continue."
                )
            }
        ), 413

    if usage_limit_reached():
        body, status = limit_reached_response()
        return jsonify(body), status

    reply, err = call_groq([{"role": "system", "content": build_system_content()}] + outgoing)
    if err:
        body, status = err
        return jsonify(body), status

    usage_now = increment_usage()
    return jsonify({"reply": reply, "source_note": source_note, "usage": usage_now})
@app.route("/test")
def test():
    return "EmesGPT is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
