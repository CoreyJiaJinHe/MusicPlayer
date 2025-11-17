import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # type: ignore

# Load environment variables from .env early
if load_dotenv:
    load_dotenv()

# Read config to determine WebEngine flags (set before importing Qt)
from mediaplayer.config.loader import load_config  # noqa: E402

cfg = load_config()
desired_flags = cfg.webengine_flags

# Default mitigations if no user flags specified
if not desired_flags:
    desired_flags = "--disable-direct-composition --autoplay-policy=no-user-gesture-required"

existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS")
if existing:
    needed = ["--disable-direct-composition", "--autoplay-policy=no-user-gesture-required"]
    extra = [f for f in needed if f not in existing.split()]
    if extra:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = existing + " " + " ".join(extra)
else:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = desired_flags

# Harden GPU path on Windows
if os.name == "nt":
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    for f in ("--disable-gpu-compositing",):
        if f not in flags:
            flags += f" {f}"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags.strip()


def _ensure_webengine_runtime_env() -> None:
    """Locate QtWebEngineProcess and resources under PySide6 and export paths."""
    try:
        import PySide6  # type: ignore
        base = Path(PySide6.__file__).parent
        # Process path
        candidates = [
            base / "Qt6" / "bin" / "QtWebEngineProcess.exe",
            base / "Qt" / "bin" / "QtWebEngineProcess.exe",
        ]
        found = [p for p in candidates if p.exists()]
        if not found:
            found = list(base.rglob("QtWebEngineProcess.exe"))
        if found and not os.environ.get("QTWEBENGINEPROCESS_PATH"):
            os.environ["QTWEBENGINEPROCESS_PATH"] = str(found[0])
        # Resources path
        res_candidates = [base / "Qt6" / "resources", base / "resources"]
        res_dir = next((p for p in res_candidates if p.exists()), None)
        if not res_dir:
            matches = list(base.rglob("qtwebengine_resources.pak"))
            if matches:
                res_dir = matches[0].parent
        if res_dir and not os.environ.get("QTWEBENGINE_RESOURCES_PATH"):
            os.environ["QTWEBENGINE_RESOURCES_PATH"] = str(res_dir)
        # Locales path (optional)
        loc_candidates = [base / "Qt6" / "translations" / "qtwebengine_locales", base / "translations" / "qtwebengine_locales"]
        loc_dir = next((p for p in loc_candidates if p.exists()), None)
        if loc_dir and not os.environ.get("QTWEBENGINE_LOCALES_PATH"):
            os.environ["QTWEBENGINE_LOCALES_PATH"] = str(loc_dir)
    except Exception:
        pass

try:
    _ensure_webengine_runtime_env()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from mediaplayer.gui.main_window import MainWindow
except Exception as e:
    print("GUI dependencies missing or failed to import:", e)
    print("Install dependencies and run again. See requirements.txt")
    sys.exit(1)


def main() -> int:
    # Improve compatibility on Windows/varied GPUs by preferring software OpenGL
    try:
        QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
    except Exception:
        pass
    # Disable sandbox to avoid issues when running as admin or under debuggers
    if os.name == "nt" and not os.environ.get("QTWEBENGINE_DISABLE_SANDBOX"):
        os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1200, 700)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
