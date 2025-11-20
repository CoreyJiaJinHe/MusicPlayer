"""Bootstrap utilities to ensure runtime data files exist.

Creates default `config.json` and `playlists.json` in the executable directory
if they are missing (first run after user deletes them or a clean install).
Safe to call multiple times; will not overwrite existing files.
"""

from __future__ import annotations

import json
import os
import sys

DEFAULT_CONFIG = {
    "music_root": "",
    "webengine_flags": None,
}

DEFAULT_PLAYLISTS = []  # start with no playlists

__all__ = ["ensure_data_files"]


def _base_dir() -> str:
    # Executable directory (PyInstaller folder build uses the dist subdir; dev runs use project root)
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def ensure_data_files(base_dir: str | None = None) -> None:
    base = base_dir or _base_dir()
    config_path = os.path.join(base, "config.json")
    playlists_path = os.path.join(base, "playlists.json")

    if not os.path.exists(config_path):
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except Exception:
            pass

    if not os.path.exists(playlists_path):
        try:
            with open(playlists_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_PLAYLISTS, f, indent=2)
        except Exception:
            pass
