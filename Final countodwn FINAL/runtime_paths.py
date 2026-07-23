"""
Resolve a stable, writable base directory for the app's runtime files
(.env, teachings.json, log files).

Why this exists: when packaged into a single .exe with PyInstaller, the
script's own __file__ (and anything bundled via --add-data) lives inside
sys._MEIPASS — a temporary folder PyInstaller extracts on every launch and
deletes on exit. Anything written there (like teachings.json) would silently
vanish the moment the app closes. This module makes sure persistent, editable
files instead live next to the .exe itself, where the user put it.

In normal `python app.py` development (not frozen), this just resolves to
this project's own folder, same as before.
"""

import os
import sys


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        # Packaged: sys.executable is the .exe itself; use its folder.
        return os.path.dirname(sys.executable)
    # Dev mode: use this file's folder (the project root).
    return os.path.dirname(os.path.abspath(__file__))
