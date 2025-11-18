from typing import Dict, List, Optional

from models import Playlist, MediaFile
from .storage import PlaylistStorage


class PlaylistManager:
    def __init__(self, storage: Optional[PlaylistStorage] = None):
        self.storage = storage or PlaylistStorage()
        self._playlists: Dict[str, Playlist] = {p.name: p for p in self.storage.load()}

    @property
    def names(self) -> List[str]:
        return list(self._playlists.keys())

    def get(self, name: str) -> Optional[Playlist]:
        return self._playlists.get(name)

    def create(self, name: str) -> Playlist:
        if name in self._playlists:
            raise ValueError(f"Playlist '{name}' already exists")
        p = Playlist(name=name, media_files=[])
        self._playlists[name] = p
        self._persist()
        return p

    def delete(self, name: str) -> None:
        if name in self._playlists:
            del self._playlists[name]
            self._persist()

    def rename(self, old: str, new: str) -> None:
        if old not in self._playlists:
            raise KeyError(old)
        if new in self._playlists:
            raise ValueError(f"Playlist '{new}' already exists")
        p = self._playlists.pop(old)
        p.name = new
        self._playlists[new] = p
        self._persist()

    def add(self, playlist: str, item: MediaFile) -> None:
        p = self._require(playlist)
        p.media_files.append(item)
        self._persist()

    def remove(self, playlist: str, index: int) -> None:
        p = self._require(playlist)
        if 0 <= index < len(p.media_files):
            del p.media_files[index]
            self._persist()

    def move(self, playlist: str, old_index: int, new_index: int) -> None:
        p = self._require(playlist)
        if 0 <= old_index < len(p.media_files) and 0 <= new_index < len(p.media_files):
            item = p.media_files.pop(old_index)
            p.media_files.insert(new_index, item)
            self._persist()

    def all(self) -> List[Playlist]:
        return list(self._playlists.values())

    def _persist(self) -> None:
        self.storage.save(self.all())

    def _require(self, name: str) -> Playlist:
        p = self.get(name)
        if not p:
            raise KeyError(name)
        return p
