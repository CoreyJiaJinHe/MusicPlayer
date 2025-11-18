from typing import List, Optional
import re
import urllib.parse
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


def _extract_video_id(url: str) -> Optional[str]:
    """Extract a YouTube video ID from common URL formats.

    Supports:
    - https://www.youtube.com/watch?v=VIDEOID
    - https://youtu.be/VIDEOID
    - https://www.youtube.com/embed/VIDEOID
    - Shorts: https://www.youtube.com/shorts/VIDEOID
    Ignores playlist (&list=) and other parameters.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return None
    host = (parsed.netloc or '').lower()
    if 'youtube.com' in host or 'youtu.be' in host:
        # watch URLs
        qs = urllib.parse.parse_qs(parsed.query)
        if 'v' in qs and qs['v']:
            return qs['v'][0]
        # youtu.be short
        if host.endswith('youtu.be'):
            vid = parsed.path.lstrip('/')
            if vid:
                return vid
        # embed or shorts path
        m = re.match(r'^/(?:embed|shorts)/([^/?#]+)', parsed.path)
        if m:
            return m.group(1)
    return None


_DUR_RE = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')


def _parse_iso8601_duration(value: str) -> int:
    """Convert an ISO8601 YouTube duration (e.g. PT1H2M3S, PT4M10S, PT55S) to seconds."""
    if not value:
        return 0
    m = _DUR_RE.match(value)
    if not m:
        return 0
    h, mnts, s = m.groups()
    total = 0
    if h:
        total += int(h) * 3600
    if mnts:
        total += int(mnts) * 60
    if s:
        total += int(s)
    return total


def from_url(api_key: str, url: str) -> Optional[OnlineMediaFile]:
    """Fetch a single YouTube video by URL. Returns None if not resolvable.

    Uses videos.list endpoint to get snippet + contentDetails for duration.
    """
    if not api_key:
        return None
    vid = _extract_video_id(url)
    if not vid:
        return None
    endpoint = 'https://www.googleapis.com/youtube/v3/videos'
    params = {
        'part': 'snippet,contentDetails',
        'id': vid,
        'key': api_key,
    }
    r = requests.get(endpoint, params=params, timeout=10)
    if r.status_code != 200:
        try:
            r.raise_for_status()
        except Exception:
            return None
    data = r.json()
    items = data.get('items') or []
    if not items:
        return None
    meta = items[0]
    snippet = meta.get('snippet', {})
    details = meta.get('contentDetails', {})
    title = snippet.get('title') or ''
    channel = snippet.get('channelTitle') or ''
    thumbs = (snippet.get('thumbnails') or {})
    thumb = thumbs.get('medium') or thumbs.get('default') or {}
    duration_iso = details.get('duration') or ''
    duration = _parse_iso8601_duration(duration_iso)
    watch_url = f'https://www.youtube.com/watch?v={vid}'
    return OnlineMediaFile(
        title=title,
        artist=channel,
        duration=duration,
        file_path='',
        provider=SourceProvider.youtube,
        url=watch_url,
        source_id=vid,
        thumbnail_url=thumb.get('url')
    )
