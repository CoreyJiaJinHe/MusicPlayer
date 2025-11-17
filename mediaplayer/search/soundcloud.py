from typing import List

from models import OnlineMediaFile, SourceProvider


def search_soundcloud(query: str) -> List[OnlineMediaFile]:
    # Placeholder: SoundCloud public search requires a client id/token.
    # For now, this returns an empty list and expects users to paste track URLs directly.
    return []

def from_url(url: str) -> OnlineMediaFile:
    return OnlineMediaFile(
        title=url,
        artist="",
        duration=0,
        file_path="",
        provider=SourceProvider.soundcloud,
        url=url,
        source_id=None,
    )
