from typing import Callable, Optional

try:
    import vlc  # type: ignore
except Exception:  # pragma: no cover - optional dependency at runtime
    vlc = None  # type: ignore


class LocalVLCPlayer:
    def __init__(self) -> None:
        self._instance = vlc.Instance() if vlc else None
        self._player = self._instance.media_player_new() if self._instance else None
        self._end_cb: Optional[Callable[[], None]] = None
        if self._player:
            events = self._player.event_manager()
            events.event_attach(self._event_code("MediaPlayerEndReached"), self._on_end)
            # Set reasonable defaults
            try:
                self._player.audio_set_mute(False)
                self._player.audio_set_volume(80)
            except Exception:
                pass

    def _event_code(self, name: str) -> int:
        return getattr(vlc.EventType, name) if vlc else 0

    def _on_end(self, event=None):  # noqa: ANN001
        if self._end_cb:
            self._end_cb()

    def on_end(self, cb: Callable[[], None]) -> None:
        self._end_cb = cb

    def play(self, file_path: str) -> None:
        if not self._player or not self._instance:
            raise RuntimeError("python-vlc is not available")
        media = self._instance.media_new_path(file_path)
        self._player.set_media(media)
        self._player.play()

    def pause(self) -> None:
        if self._player:
            self._player.pause()

    def stop(self) -> None:
        if self._player:
            self._player.stop()

    def set_volume(self, volume: int) -> None:
        if self._player:
            self._player.audio_set_volume(max(0, min(100, volume)))

    # --- Query helpers for status display ---
    def get_time_ms(self) -> int:
        return int(self._player.get_time()) if self._player else 0

    def get_length_ms(self) -> int:
        return int(self._player.get_length()) if self._player else 0

    def is_playing(self) -> bool:
        return bool(self._player and self._player.is_playing())
