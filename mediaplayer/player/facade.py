import logging
from typing import Callable, Optional

from models import MediaFile, OnlineMediaFile, SourceProvider
from .local_vlc import LocalVLCPlayer
from .web_embed import WebEmbedPlayer


class PlayerFacade:
    def __init__(self, web_parent=None) -> None:  # noqa: ANN001
        self.local = LocalVLCPlayer()
        self._web_init_error: Optional[str] = None
        try:
            self.web = WebEmbedPlayer(web_parent)
        except Exception:
            self.web = None
            # Capture the error detail for diagnostics
            try:
                import sys
                self._web_init_error = str(sys.exc_info()[1])
            except Exception:
                self._web_init_error = "Unknown WebEngine initialization error"
        self._web_parent = web_parent
        self._on_end: Optional[Callable[[], None]] = None

    def web_widget(self):  # noqa: ANN201
        return self.web.widget() if self.web else None

    def ensure_web(self, parent=None) -> bool:  # noqa: ANN001
        if self.web:
            return True
        # Remember the best-known parent for subsequent initializations
        if parent is not None:
            self._web_parent = parent
        try:
            self.web = WebEmbedPlayer(self._web_parent)
            if self._on_end:
                self.web.on_end(self._on_end)
            return True
        except Exception as e:
            self.web = None
            self._web_init_error = str(e)
            raise RuntimeError(f"Web player initialization failed: {e}")

    def on_end(self, cb: Callable[[], None]) -> None:
        self._on_end = cb
        self.local.on_end(cb)
        if self.web:
            self.web.on_end(cb)

    def play(self, item: MediaFile) -> None:
        if isinstance(item, OnlineMediaFile) or item.provider in (
            SourceProvider.youtube,
            SourceProvider.soundcloud,
        ):
            # Lazily initialize web player if needed
            if not self.web:
                self.ensure_web(self._web_parent)
            if not self.web:
                raise RuntimeError("Web player not available for online items")
            if item.provider == SourceProvider.youtube and item.source_id:
                self.web.load_youtube(item.source_id)
                logging.warning("Loading YouTube video ID: %s", item.source_id)
            elif item.provider == SourceProvider.soundcloud and item.url:
                self.web.load_soundcloud(item.url)
            else:
                # Fallback: try direct URL if provided
                self.web.load(getattr(item, "url", ""))
        else:
            self.local.play(item.file_path)

    def pause(self) -> None:
        self.local.pause()
        if self.web:
            try:
                self.web.pause()
            except Exception:
                pass

    def stop(self) -> None:
        self.local.stop()
        if self.web:
            try:
                self.web.stop()
            except Exception:
                pass

    def set_volume(self, volume: int) -> None:
        self.local.set_volume(volume)
        if self.web:
            self.web.set_volume(volume)
