"""
PyInstaller entry point for the packaged EmesGPT.exe.

Not used for normal `python app.py` development — that keeps working exactly
as it always has. This script is the thing PyInstaller compiles into the
.exe: it starts the same Flask app in production mode (no debug/reloader,
since PyInstaller and Werkzeug's auto-reloader actively conflict — the
reloader tries to re-exec the process, which doesn't work once it's a frozen
binary) and opens the user's default browser automatically once the server
is actually ready. Double-clicking the .exe should be the entire experience:
no terminal, no typed commands, no visible console window.
"""

import os
import socket
import sys
import threading
import time
import webbrowser

from runtime_paths import get_base_dir

BASE_DIR = get_base_dir()
LOG_PATH = os.path.join(BASE_DIR, "emesgpt.log")
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", 5000))


def _redirect_streams_for_windowed_build():
    """A --noconsole PyInstaller build has no console, so sys.stdout/stderr
    are None. Werkzeug's dev server prints a startup banner and will crash
    the first time anything tries to write to a None stream. Send output to
    a log file next to the exe instead, so there's still somewhere to look
    if something goes wrong."""
    if sys.stdout is None or sys.stderr is None:
        try:
            log = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        except OSError:
            log = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = log
        sys.stderr = log


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def _open_browser_once_ready():
    # Poll briefly instead of a blind sleep — the server is usually ready in
    # well under a second, but this tolerates a slow first launch too.
    for _ in range(50):  # ~10s max
        if not _port_is_free(HOST, PORT):
            break
        time.sleep(0.2)
    webbrowser.open(f"http://{HOST}:{PORT}")


def _show_fatal_error(message: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except OSError:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            f"{message}\n\nDetails were written to:\n{LOG_PATH}",
            "EmesGPT",
            0x10,  # MB_ICONERROR
        )
    except Exception:
        # Not on Windows, or ctypes unavailable — the log file is the fallback.
        pass


def main():
    _redirect_streams_for_windowed_build()

    if not _port_is_free(HOST, PORT):
        # Most likely EmesGPT is already running from an earlier launch.
        # Just open a browser tab to it instead of erroring out.
        webbrowser.open(f"http://{HOST}:{PORT}")
        return

    try:
        from app import app  # noqa: PLC0415 - imported here so any load-time
        # error (missing template, bad import, etc.) is caught below instead
        # of crashing silently before main() can log/report it.
    except Exception as exc:  # noqa: BLE001
        _show_fatal_error(f"EmesGPT failed to start while loading the app:\n{exc}")
        return

    threading.Thread(target=_open_browser_once_ready, daemon=True).start()

    try:
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
    except Exception as exc:  # noqa: BLE001
        _show_fatal_error(f"EmesGPT crashed:\n{exc}")


if __name__ == "__main__":
    main()
