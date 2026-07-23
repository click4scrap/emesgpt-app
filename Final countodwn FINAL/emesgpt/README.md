# EmesGPT — prototype

A DeepSeek-powered wrapper (no model training involved): a system prompt defines
EmesGPT's voice and mission, a small context-stuffed knowledge base supplies your
narrative modules, and every request is a single API call to DeepSeek's
chat-completions endpoint.

## What's here

- `app.py` — Flask backend.
  - `/api/chat` (used by the UI) — conversational. The client sends the full
    running message history each turn; the server prepends the system prompt
    + knowledge base and forwards everything to DeepSeek, so it has full
    context — the same way a normal chat with DeepSeek works.
  - `/api/analyze` — one-shot analysis, kept for backward compatibility /
    scripted single-call use. No memory between calls.
  - Both auto-fetch the YouTube transcript via `youtube-transcript-api` if
    the user's message is a bare YouTube URL.
  - `/teach` serves the teaching wizard; `/api/teach/*` routes back it — see
    "Teaching mode" below.
  - `/api/usage` (GET) and `/api/usage/reset` (POST) back the 10-message
    session limit — see "Message limit" below.
- `knowledge.py` — the system prompt and the three full narrative modules,
  fed to the model verbatim as background context.
- `teachings.py` — storage for the teaching wizard's answers: reads/writes
  `teachings.json` on disk and renders saved answers for injection into the
  system prompt.
- `templates/index.html` — chat-style frontend: scrolling message history,
  bottom input bar, Export and Clear history buttons. The full conversation
  is saved to the browser's `localStorage` (so it survives reloads), but only
  the last 10 messages are sent to `/api/chat` as context on each turn — see
  "Cost control" below.
- `templates/teach.html` — the teaching wizard (see below).
- `requirements.txt` — Python dependencies.

## Setup

1. **Install Python 3.9+** if you don't have it already.

2. **Install dependencies:**
   ```bash
   cd emesgpt
   pip install -r requirements.txt
   ```

3. **Set your DeepSeek API key.** Get one from https://platform.deepseek.com,
   then either:

   - Copy `.env.example` to `.env` and fill it in:
     ```bash
     cp .env.example .env
     # edit .env and paste your key
     ```
   - Or export it directly in your shell:
     ```bash
     export DEEPSEEK_API_KEY=sk-your-key-here
     ```

4. **Run the app:**
   ```bash
   python app.py
   ```
   By default it serves on http://localhost:5000 — open that in your browser.

## Using it

Paste an article, a speech transcript, or just a YouTube link into the box and
hit **Send**. For a bare YouTube URL, the app fetches captions automatically;
if a video has no captions available, it'll tell you to paste the transcript
manually (e.g. via a tool like DownSub).

Keep chatting — you can ask follow-ups ("who specifically benefits?", "what's
the strongest counterargument?") without re-pasting context. Click **Clear
history** to wipe the conversation and start fresh (e.g. before pasting an
unrelated article), or **Export** to download the full conversation as a
timestamped `.txt` file.

## Cost control: the context window

The full conversation is kept in your browser (`localStorage`) and shown on
screen, so nothing is ever lost from your view. But only the **last 10
messages** (roughly 5 exchanges) are actually sent to DeepSeek as context on
each turn — older messages are dimmed in the UI and a divider marks where the
"sent to model" window begins. This keeps token usage, and therefore cost,
roughly constant no matter how long a conversation runs, at the cost of
EmesGPT "forgetting" anything further back than the window.

To change the window size, edit `CONTEXT_WINDOW` near the top of the
`<script>` block in `templates/index.html` (a sensible range is 6–20;
higher = more memory but higher cost per message). There's no server-side
change needed — the backend just forwards whatever message list the client
sends.

## Teaching mode

Click **Teach EmesGPT** (top of the chat page), or go to `/teach` directly.
It's a one-question-at-a-time wizard: 10 prewritten questions about your
beliefs and how EmesGPT should behave, plus you can add your own custom
questions or ask it to suggest an AI-generated follow-up based on your last
answer. Skip anything you don't want to answer.

Every answer is saved immediately to `teachings.json` (created next to
`app.py` on first save) — that's the "save it on my computer" part, since
you're running this server locally. There's no separate injection step:
`build_system_content()` in `app.py` re-reads `teachings.json` on **every**
request (both `/api/chat` and `/api/analyze`) and appends a "Personal
Teachings" section after the knowledge-base modules, so answers take effect
immediately, with no restart needed. Reopening the wizard later resumes
where you left off, with previous answers pre-filled and editable.

`teachings.json` holds your personal answers, so it's listed in `.gitignore`
alongside `.env` — don't commit it or share it if you push this repo
anywhere. "Reset all teachings" on the wizard's finish screen wipes it.

## Message limit

The server enforces a hard cap of **10 messages** per run on the **main chat
interface only** — checked server-side before every DeepSeek call in
`/api/chat` and `/api/analyze`, so it can't be bypassed by editing the page.
A 429 fires before hitting the API at all once it's used up (confirmed by
mock-testing: exactly N real DeepSeek calls happen for N allowed chat
messages, never one more).

The **teaching wizard is deliberately exempt** — `/api/teach/suggest-followup`
never checks or increments this counter, so a long teaching session won't get
cut off mid-conversation. Verified: with the chat limit set to 3 and
exhausted, 5 subsequent teaching follow-up calls all still succeeded and the
usage counter stayed unchanged at 3/3. Everything else about teaching mode
(saving answers, reviewing/editing, resetting all teachings) was never
limited in the first place — only the AI-generated-follow-up convenience
feature makes a DeepSeek call at all.

It's a single counter shared by the whole running server for chat, not per
conversation — if you open two chat tabs, they draw from the same pool of
10. It's stored in memory only (nothing written to disk), so **restarting
the server zeroes it out automatically**. You can also reset it early
without restarting: click **Reset limit** in the bar above the message box
on the chat page (or `POST /api/usage/reset` directly).

To change the cap, set `MESSAGE_LIMIT` (e.g. `MESSAGE_LIMIT=25 python app.py`)
or edit the default in `app.py`.

## Notes for going further

- The knowledge base is currently "context stuffing" — all three modules are
  sent on every request. That's fine at this size. If you add many more long
  chapters later, switch to real vector retrieval (embed each chunk, fetch
  only the top few relevant to the pasted text) so you don't blow past
  context-length or cost limits.
- Conversation history lives in the browser's `localStorage`, scoped to that
  browser profile — clearing browser data or switching browsers loses it.
  There's no server-side storage. `MAX_CONVERSATION_CHARS` (backend, default
  150,000 chars) is a secondary guardrail in case you raise `CONTEXT_WINDOW`
  a lot; the primary cost control is the 10-message window above.
- This is an MVP: no auth, no rate limiting, no persistence. Don't deploy it
  publicly as-is with your API key exposed — put it behind login and a reverse
  proxy first, and consider a request cap per user.
