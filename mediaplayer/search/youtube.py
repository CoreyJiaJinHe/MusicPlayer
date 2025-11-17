from typing import List
import requests

from models import OnlineMediaFile, SourceProvider


def search_youtube(api_key: str, query: str, max_results: int = 10) -> List[OnlineMediaFile]:
    if not api_key:
        return []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "key": api_key,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    items = []
    for item in data.get("items", []):
        vid = item["id"].get("videoId")
        snippet = item.get("snippet", {})
        title = snippet.get("title", "")
        thumbs = snippet.get("thumbnails", {})
        thumb = thumbs.get("medium") or thumbs.get("default") or {}
        url_watch = f"https://www.youtube.com/watch?v={vid}"
        items.append(
            OnlineMediaFile(
                title=title,
                artist=snippet.get("channelTitle", ""),
                duration=0,
                file_path="",
                provider=SourceProvider.youtube,
                url=url_watch,
                source_id=vid,
                thumbnail_url=thumb.get("url"),
            )
        )
    return items
