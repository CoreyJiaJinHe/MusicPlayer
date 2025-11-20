import sys
from PySide6.QtWidgets import QApplication
try:
    from MusicPlayer.version import __version__
except Exception:
    __version__ = "1.0.0"
try:
    from MusicPlayer.bootstrap import ensure_data_files
except Exception:
    def ensure_data_files():
        pass

# Import MainWindow from your package
try:
    from MusicPlayer.gui.main_window import MainWindow  # Current package name
except ModuleNotFoundError:
    # Fallback in case the package is named lowercase in your environment
    from musicplayer.gui.main_window import MainWindow  # noqa: F401


def main() -> int:
    app = QApplication(sys.argv)
    # Ensure default data files exist beside the executable.
    try:
        ensure_data_files()
    except Exception:
        pass
    win = MainWindow()
    win.resize(1200, 800)
    try:
        win.setWindowTitle(f"Music Player v{__version__}")
    except Exception:
        pass
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
