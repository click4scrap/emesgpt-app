# EmesGPT — prototype

A Groq-powered wrapper (no model training involved): a system prompt defines
EmesGPT's voice and mission, a small context-stuffed knowledge base supplies your
narrative modules, and every request is a single API call to Groq's
chat-completions endpoint.

## What's here

- `app.py` — Flask backend.
  - `/api/chat` (used by the UI) — conversational. The client sends the full
    running message history each turn; the server prepends the system prompt
    + knowledge base and forwards everything to Groq, so it has full
    context — the same way a normal chat with Groq works.
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
- `runtime_paths.py` — resolves a stable folder for `.env`/`teachings.json`/logs:
  the project folder in normal dev use, or the `.exe`'s own folder when
  packaged (see "Windows .exe" below).
- `launcher.py` — entry point used only when packaging into a `.exe`; not
  used by `python app.py`.
- `.github/workflows/build-windows-exe.yml` — builds the `.exe` on GitHub's
  servers (see below).

## Setup

1. **Install Python 3.9+** if you don't have it already.

2. **Install dependencies:**
   ```bash
   cd emesgpt
   pip install -r requirements.txt
   ```

3. **Set your Groq API key.** Get one from https://console.groq.com/keys,
   then either:

   - Copy `.env.example` to `.env` and fill it in:
     ```bash
     cp .env.example .env
     # edit .env and paste your key
     ```
   - Or export it directly in your shell:
     ```bash
     export GROQ_API_KEY=gsk-your-key-here
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
messages** (roughly 5 exchanges) are actually sent to Groq as context on
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

Go to `/teach` directly in your browser — it's a hidden route with no link
from the main chat page, by design. It's a one-question-at-a-time wizard:
10 prewritten questions about your
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
interface only** — checked server-side before every Groq call in
`/api/chat` and `/api/analyze`, so it can't be bypassed by editing the page.
A 429 fires before hitting the API at all once it's used up (confirmed by
mock-testing: exactly N real Groq calls happen for N allowed chat
messages, never one more).

The **teaching wizard is deliberately exempt** — `/api/teach/suggest-followup`
never checks or increments this counter, so a long teaching session won't get
cut off mid-conversation. Verified: with the chat limit set to 3 and
exhausted, 5 subsequent teaching follow-up calls all still succeeded and the
usage counter stayed unchanged at 3/3. Everything else about teaching mode
(saving answers, reviewing/editing, resetting all teachings) was never
limited in the first place — only the AI-generated-follow-up convenience
feature makes a Groq call at all.

It's a single counter shared by the whole running server for chat, not per
conversation — if you open two chat tabs, they draw from the same pool of
10. It's stored in memory only (nothing written to disk), so **restarting
the server zeroes it out automatically**. You can also reset it early
without restarting: click **Reset limit** in the bar above the message box
on the chat page (or `POST /api/usage/reset` directly).

To change the cap, set `MESSAGE_LIMIT` (e.g. `MESSAGE_LIMIT=25 python app.py`)
or edit the default in `app.py`.

## Windows .exe: no Python, no terminal, ever

A real Windows `.exe` can't be cross-compiled reliably from Linux/Mac, so
instead of a sketchy cross-build, this repo includes a GitHub Actions
workflow (`.github/workflows/build-windows-exe.yml`) that builds it on
GitHub's own Windows servers — for free, with a genuine Windows Python and
PyInstaller. You never install Python or open a terminal at any point in
this process; it's all done through a web browser.

**One-time setup:**

1. Create a free account at github.com if you don't have one.
2. Create a new repository (the "+" in the top right → "New repository").
   It can be private.
3. On the new repo's page, click **Add file → Upload files**, then drag the
   `emesgpt` folder's contents in and click **Commit changes**. **Do not
   include your `.env` file** — it has your real Groq key in plain text, and
   `.gitignore` only stops that from happening with `git`, not with this
   drag-and-drop web uploader, which will happily upload whatever you drop
   on it. Drag in `.env.example` instead (no real key inside), or just leave
   `.env`/`.env.example` out of the upload entirely; either way you'll add a
   real `.env` next to the finished `.exe` in step 2 of "Running it" below.
   `teachings.json` and any `__pycache__` folder are similarly fine to leave
   out — they'll regenerate.
4. Click the **Actions** tab. The "Build Windows EXE" workflow starts
   automatically after the upload (uploading counts as a push to `main`).
   It takes a couple of minutes.
5. Once it shows a green checkmark, click into that run, scroll to
   **Artifacts**, and download **EmesGPT-windows** — a zip containing
   `EmesGPT.exe`, `.env.example`, and this README.

**Running it:**

1. Unzip `EmesGPT-windows.zip` anywhere you like (Desktop, a folder, a USB
   drive — it's fully portable).
2. Next to `EmesGPT.exe`, create a file named `.env` (rename the included
   `.env.example`, or make a new text file and name it exactly `.env`) with
   one line: `GROQ_API_KEY=your_actual_key`. This is a one-time edit in
   Notepad — still no terminal.
3. Double-click `EmesGPT.exe`. A browser tab opens to the app automatically
   after a second or two. That's it — from here on, it's just double-click
   and go.

**A couple of things to expect the first time:**

- Windows SmartScreen will likely show "Windows protected your PC" the
  first time you run it, because the `.exe` isn't code-signed (a signing
  certificate costs money and isn't practical for a personal one-off tool).
  Click **More info → Run anyway**. This is normal for small, unsigned
  Windows executables, not a sign anything's wrong.
- Some antivirus tools flag PyInstaller `--onefile` executables as
  suspicious purely because of how they self-extract at startup — a common
  false positive with this packaging method, not specific to this app.
- `teachings.json` and `emesgpt.log` (only created if something goes wrong)
  will appear next to `EmesGPT.exe` after first use — that's expected and
  is what makes your teaching-mode answers persist between launches.
- If you ever see nothing happen when double-clicking, or the browser
  doesn't open, check for `emesgpt.log` next to the exe — startup errors are
  written there since there's no console to show them in.
- Rebuilding after a code change: edit files in the GitHub repo (or
  re-upload changed files) and the workflow reruns automatically; download
  the new artifact the same way.

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
