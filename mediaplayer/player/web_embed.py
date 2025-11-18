import logging
import os
import socket
import threading
from typing import Callable, Optional

# Core Qt
try:
    from PySide6.QtCore import QUrl, QObject, Slot
except Exception:  # pragma: no cover - runtime optional
    QUrl = None  # type: ignore
    QObject = object  # type: ignore
    def Slot(*args, **kwargs):  # type: ignore
        def inner(f):
            return f
        return inner

# WebEngine (required for embedded playback)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMessageBox
#settings = view.settings() # This is how you get the QWebEngineSettings object

# WebChannel (optional: used for end events and volume)
try:
    from PySide6.QtWebChannel import QWebChannel
except Exception:  # pragma: no cover - runtime optional
    QWebChannel = None  # type: ignore


def _assets_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "web_assets")


# Lightweight HTTP server to serve web assets over http://127.0.0.1:<port>
_SERVER_LOCK = threading.Lock()
_SERVER_PORT: Optional[int] = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ensure_http_server() -> str:
    """Start a background HTTP server for web assets if not running; return base URL."""
    global _SERVER_PORT
    if _SERVER_PORT is not None:
        return f"http://127.0.0.1:{_SERVER_PORT}"
    with _SERVER_LOCK:
        if _SERVER_PORT is not None:
            return f"http://127.0.0.1:{_SERVER_PORT}"
        try:
            import http.server
            import socketserver

            class QuietHandler(http.server.SimpleHTTPRequestHandler):  # type: ignore[misc]
                def log_message(self, format, *args):  # noqa: A003 - method signature
                    try:
                        logging.debug("HTTP: " + format, *args)
                    except Exception:
                        pass

            port = _find_free_port()
            handler = lambda *args, directory=_assets_dir(): QuietHandler(*args, directory=directory)  # type: ignore[misc]
            httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
            httpd.daemon_threads = True

            def _serve():
                try:
                    httpd.serve_forever()
                except Exception:
                    pass

            t = threading.Thread(target=_serve, name="WebAssetsServer", daemon=True)
            t.start()
            _SERVER_PORT = port
            logging.warning("Web assets HTTP server started at http://127.0.0.1:%s", port)
        except Exception as e:
            logging.error("Failed to start web assets server: %s", e)
            raise
    return f"http://127.0.0.1:{_SERVER_PORT}"


def _player_file_url(params: str) -> str:
    base = _ensure_http_server()
    url = f"{base}/player.html?{params}"
    logging.warning("Generating player HTTP URL: %s", url)
    return url


def youtube_player_url(video_id: str) -> str:
    # Use local wrapper so app can control pause/stop/volume via JS
    from urllib.parse import urlencode
    url = _player_file_url(urlencode({"type": "youtube", "id": video_id}))
    logging.warning("Generating YouTube wrapper URL: %s", url)
    return url
#https://youtu.be/Qb487v1Nb6U?list=RDQ16eQY1yuSo
#url = f"https://www.youtube.com/embed/{video_id}


def soundcloud_player_url(track_url: str) -> str:
    from urllib.parse import urlencode

    return _player_file_url(urlencode({"type": "soundcloud", "url": track_url}))


class _Bridge(QObject):
    def __init__(self, on_end_cb: Optional[Callable[[], None]] = None) -> None:
        super().__init__()
        self._on_end = on_end_cb

    @Slot()
    def onEnded(self) -> None:  # noqa: N802 - Qt naming
        if self._on_end:
            self._on_end()


class WebEmbedPlayer:
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        # Try to construct the view and surface underlying errors
        try:
            self.view = QWebEngineView(parent)
        except Exception as e:
            logging.warning("Failed to create QWebEngineView: %s", e)
            raise RuntimeError(f"Failed to create QWebEngineView: {e}")
        self._bridge = _Bridge()
        self._channel = None
        logging.warning("Setting up WebChannel for WebEmbedPlayer")
        try:
            if QWebChannel:
                self._channel = QWebChannel(self.view.page())
                self._channel.registerObject("bridge", self._bridge)
                self.view.page().setWebChannel(self._channel)
        except Exception:
            self._channel = None
        logging.warning("WebChannel setup complete: %s", self._channel is not None)
        # Allow autoplay without user gestures and permit local HTML to access remote URLs
        try:
            s = self.view.settings()
            SettingsCls = type(s)
            s.setAttribute(SettingsCls.WebAttribute.PlaybackRequiresUserGesture, False)
        except Exception:
            pass
        try:
            s = self.view.settings()
            SettingsCls = type(s)
            s.setAttribute(SettingsCls.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        except Exception:
            pass
        # View will be embedded; do not call show() here
        # Navigation result toast
        try:
            self.view.loadFinished.connect(self._on_load_finished)  # type: ignore[attr-defined]
        except Exception:
            pass

        self._last_url: Optional[str] = None

    def widget(self):  # noqa: ANN201
        return self.view

    def on_end(self, cb: Callable[[], None]) -> None:
        self._bridge._on_end = cb  # type: ignore[attr-defined]

    def load(self, url: str) -> None:
        logging.warning("Loading URL: %s", url)
        self._last_url = url
        self.view.setUrl(QUrl(url))

    def _on_load_finished(self, ok: bool) -> None:  # noqa: ANN001
        if not ok:
            try:
                parent = self.view.parent()
                QMessageBox.warning(parent if isinstance(parent, object) else None, "Navigation Failed", f"Failed to load: {self._last_url or ''}")
            except Exception:
                pass

    def load_youtube(self, video_id: str) -> None:
        logging.warning("Attempting to Loading YouTube video ID: %s", video_id)
        logging.warning("YouTube player URL: %s", youtube_player_url(video_id))
        self.load(youtube_player_url(video_id))

    def load_soundcloud(self, track_url: str) -> None:
        self.load(soundcloud_player_url(track_url))

    def set_volume(self, volume: int) -> None:
        # 0-100
        try:
            self.view.page().runJavaScript(f"window.setVolume && window.setVolume({int(max(0,min(100,volume)))})")
        except Exception:
            pass

    def pause(self) -> None:
        try:
            self.view.page().runJavaScript("window.pausePlayback && window.pausePlayback()")
        except Exception:
            pass

    def resume(self) -> None:
        try:
            self.view.page().runJavaScript("window.resumePlayback && window.resumePlayback()")
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self.view.page().runJavaScript("window.stopPlayback && window.stopPlayback()")
        except Exception:
            pass
