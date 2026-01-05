from typing import List, Optional, Tuple
import re
import urllib.parse
import requests

from models import OnlineMediaFile, SourceProvider, YoutubeChannel


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


def search_youtube_channels(api_key: str, query: str, max_results: int = 10) -> List[YoutubeChannel]:
    """Search YouTube for channels by name/keyword.

    Returns a list of YoutubeChannel. Thumbnail URLs (when needed for UI) can be
    read from the search result's snippet; for now, callers can refetch or we
    can attach as ad-hoc attribute on the dataclass instance.
    """
    if not api_key:
        return []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": max_results,
        "key": api_key,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    results: List[YoutubeChannel] = []
    for item in data.get("items", []):
        cid = (item.get("id") or {}).get("channelId")
        snip = item.get("snippet", {})
        if not cid:
            continue
        channel_url = f"https://www.youtube.com/channel/{cid}"
        ch = YoutubeChannel(source_url=channel_url, channel_id=cid, channel_name=snip.get("channelTitle", ""))
        # Attach thumbnail URL as an attribute for UI convenience
        thumbs = (snip.get("thumbnails") or {})
        thumb = thumbs.get("medium") or thumbs.get("default") or {}
        setattr(ch, "thumbnail_url", thumb.get("url"))
        results.append(ch)
    return results


def _extract_channel_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Attempt to extract a channelId or handle from a YouTube channel URL.

    Returns (channel_id, handle). Exactly one will be non-None if detected.
    Supports:
    - https://www.youtube.com/channel/UCxxxx
    - https://www.youtube.com/@handle
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return None, None
    host = (parsed.netloc or '').lower()
    if 'youtube.com' not in host:
        return None, None
    path = parsed.path or ''
    # /channel/UC...
    m = re.match(r"^/channel/([A-Za-z0-9_-]+)", path)
    if m:
        return m.group(1), None
    # /@handle or /@handle/...
    m2 = re.match(r"^/@([A-Za-z0-9._-]+)", path)
    if m2:
        return None, m2.group(1)
    return None, None


def resolve_channel_id(api_key: str, text: str) -> Optional[str]:
    """Resolve a channel identifier from user input which may be:
    - a channel ID (starts with 'UC')
    - a YouTube channel URL (/channel/UC...)
    - a handle URL (/@handle)
    - a bare handle starting with '@'
    """
    if not text:
        return None
    t = text.strip()
    # direct channel ID
    if t.startswith('UC') and len(t) >= 10:
        return t
    # URL forms
    if t.lower().startswith('http://') or t.lower().startswith('https://'):
        cid, handle = _extract_channel_from_url(t)
        if cid:
            return cid
        if handle:
            # search for channels with the handle as query
            chans = search_youtube_channels(api_key, handle, max_results=1)
            return chans[0].channel_id if chans else None
        return None
    # bare handle like @reina...
    if t.startswith('@'):
        handle = t[1:]
        chans = search_youtube_channels(api_key, handle, max_results=1)
        return chans[0].channel_id if chans else None
    return None


def list_channel_videos(api_key: str, channel_id: str, max_results: int = 25, page_token: Optional[str] = None) -> Tuple[List[OnlineMediaFile], Optional[str]]:
    """List videos using the channel's uploads playlist for canonical ordering.

    This aligns with the browser's Videos tab (date-added order). Supports pagination
    via nextPageToken. max_results is capped at 50 by the API.
    """
    if not api_key or not channel_id:
        return [], None
    # First, get the uploads playlist ID for the channel
    channels_ep = "https://www.googleapis.com/youtube/v3/channels"
    ch_params = {
        "part": "contentDetails",
        "id": channel_id,
        "key": api_key,
    }
    cr = requests.get(channels_ep, params=ch_params, timeout=10)
    cr.raise_for_status()
    cdata = cr.json()
    items_c = cdata.get("items") or []
    if not items_c:
        return [], None
    uploads_pl = (items_c[0].get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads_pl:
        return [], None
    # Then list items from the uploads playlist
    yt_api = "https://www.googleapis.com/youtube/v3/playlistItems"
    params = {
        "part": "snippet,contentDetails",
        "playlistId": uploads_pl,
        "maxResults": min(max_results or 25, 50),
        "key": api_key,
    }
    if page_token:
        params["pageToken"] = page_token
    r = requests.get(yt_api, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    next_token = data.get("nextPageToken")
    results: List[OnlineMediaFile] = []
    for it in data.get("items", []):
        snip = it.get("snippet", {})
        vid = (snip.get("resourceId") or {}).get("videoId")
        if not vid:
            continue
        title = snip.get("title") or "(untitled)"
        channel = snip.get("videoOwnerChannelTitle") or snip.get("channelTitle") or ""
        thumbs = (snip.get("thumbnails") or {})
        thumb = thumbs.get("medium") or thumbs.get("default") or {}
        watch = f"https://www.youtube.com/watch?v={vid}"
        # Optionally include duration when available (contentDetails may have it)
        # Not all playlistItems contentDetails have duration; separate call would be needed.
        mf = OnlineMediaFile(
            title=title,
            artist=channel,
            duration=0,
            file_path="",
            provider=SourceProvider.youtube,
            url=watch,
            source_id=vid,
            thumbnail_url=thumb.get("url"),
        )
        try:
            setattr(mf, "published_at", snip.get("publishedAt"))
        except Exception:
            pass
        results.append(mf)
    return results, next_token

