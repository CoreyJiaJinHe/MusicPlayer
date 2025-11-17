import json
import os
from dataclasses import asdict
from typing import List, Union, Dict, Any

from models import MediaFile, OnlineMediaFile, Playlist, SourceProvider


DEFAULT_PLAYLISTS_PATH = os.path.join(os.getcwd(), "playlists.json")


def _mediafile_to_dict(item: Union[MediaFile, OnlineMediaFile]) -> Dict[str, Any]:
    data = asdict(item)
    # Enum to value
    if isinstance(item.provider, SourceProvider):
        data["provider"] = item.provider.value
    return data


def _dict_to_mediafile(d: Dict[str, Any]) -> Union[MediaFile, OnlineMediaFile]:
    provider_val = d.get("provider", SourceProvider.local)
    provider = (
        provider_val if isinstance(provider_val, SourceProvider) else SourceProvider(provider_val)
    )
    if provider in (SourceProvider.youtube, SourceProvider.soundcloud) or d.get("url"):
        return OnlineMediaFile(
            title=d.get("title", ""),
            artist=d.get("artist", ""),
            duration=int(d.get("duration", 0)),
            file_path=d.get("file_path", ""),
            provider=provider,
            note=d.get("note"),
            url=d.get("url", ""),
            source_id=d.get("source_id"),
            streaming_quality=d.get("streaming_quality"),
            thumbnail_url=d.get("thumbnail_url"),
        )
    return MediaFile(
        title=d.get("title", ""),
        artist=d.get("artist", ""),
        duration=int(d.get("duration", 0)),
        file_path=d.get("file_path", ""),
        provider=provider,
        note=d.get("note"),
    )


class PlaylistStorage:
    def __init__(self, path: str = DEFAULT_PLAYLISTS_PATH):
        self.path = path

    def load(self) -> List[Playlist]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        playlists: List[Playlist] = []
        for p in raw or []:
            items = [_dict_to_mediafile(it) for it in p.get("media_files", [])]
            playlists.append(Playlist(name=p.get("name", ""), media_files=items))
        return playlists

    def save(self, playlists: List[Playlist]) -> None:
        wire = []
        for p in playlists:
            wire.append(
                {
                    "name": p.name,
                    "media_files": [_mediafile_to_dict(it) for it in p.media_files],
                }
            )
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(wire, f, indent=2)
