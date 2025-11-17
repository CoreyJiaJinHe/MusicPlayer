import os
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
#settings = view.settings() # This is how you get the QWebEngineSettings object

# WebChannel (optional: used for end events and volume)
try:
    from PySide6.QtWebChannel import QWebChannel
except Exception:  # pragma: no cover - runtime optional
    QWebChannel = None  # type: ignore


def _asset_path() -> str:
    return os.path.join(os.path.dirname(__file__), "web_assets", "player.html")


def _player_file_url(params: str) -> str:
    path = _asset_path()
    path = os.path.abspath(path)
    return QUrl.fromLocalFile(path).toString() + ("?" + params)


def youtube_player_url(video_id: str) -> str:
    from urllib.parse import urlencode

    return _player_file_url(urlencode({"type": "youtube", "id": video_id}))


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
            raise RuntimeError(f"Failed to create QWebEngineView: {e}")
        self._bridge = _Bridge()
        self._channel = None
        try:
            if QWebChannel:
                self._channel = QWebChannel(self.view.page())
                self._channel.registerObject("bridge", self._bridge)
                self.view.page().setWebChannel(self._channel)
        except Exception:
            self._channel = None
        # Allow autoplay without user gestures (Qt setting)
        try:
            self.view.settings().setAttribute(self.view.settings().PlaybackRequiresUserGesture, False)
        except Exception:
            pass

    def widget(self):  # noqa: ANN201
        return self.view

    def on_end(self, cb: Callable[[], None]) -> None:
        self._bridge._on_end = cb  # type: ignore[attr-defined]

    def load(self, url: str) -> None:
        self.view.setUrl(QUrl(url))

    def load_youtube(self, video_id: str) -> None:
        self.load(youtube_player_url(video_id))

    def load_soundcloud(self, track_url: str) -> None:
        self.load(soundcloud_player_url(track_url))

    def set_volume(self, volume: int) -> None:
        # 0-100
        try:
            self.view.page().runJavaScript(f"window.setVolume && window.setVolume({int(max(0,min(100,volume)))})")
        except Exception:
            pass
