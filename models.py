from dataclasses import dataclass
from enum import Enum
from typing import Optional, List


class SourceProvider(str, Enum):
    local = "local"
    youtube = "youtube"
    soundcloud = "soundcloud"


@dataclass
class MediaFile:
    title: str
    artist: str
    duration: int  # Duration in seconds
    file_path: str  # For local media; may be empty for online items
    provider: SourceProvider = SourceProvider.local
    note: Optional[str] = None
    unavailable: bool = False  # Flag for unplayable tracks (e.g., YouTube restrictions)
    
@dataclass
class Playlist:
    name: str
    media_files: List[MediaFile]
    source_url: Optional[str] = None


@dataclass
class OnlineMediaFile(MediaFile):
    # Defaults are required because base class ends with a default field (note)
    # and dataclass requires all non-defaults precede defaults across the MRO.
    url: str = ""  # Source URL (YouTube watch URL or SoundCloud permalink)
    source_id: Optional[str] = None  # e.g., YouTube video ID or SoundCloud track ID
    streaming_quality: Optional[str] = None  # e.g., '1080p', '720p', '480p'
    thumbnail_url: Optional[str] = None

@dataclass
class YoutubeChannel:
    # Channel search result descriptor
    source_url: str
    channel_id: str
    channel_name: str


__all__ = ["MediaFile", "Playlist", "OnlineMediaFile", "SourceProvider"]
    
    
__all__ = ["MediaFile", "Playlist", "OnlineMediaFile"]
    