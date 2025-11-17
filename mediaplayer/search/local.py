import os
from typing import List

from models import MediaFile, SourceProvider


SUPPORTED_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}


def search_local(root: str, query: str = "") -> List[MediaFile]:
    results: List[MediaFile] = []
    q = (query or "").lower()
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in SUPPORTED_EXTS:
                continue
            if q and q not in fn.lower():
                continue
            full = os.path.join(dirpath, fn)
            results.append(
                MediaFile(
                    title=os.path.splitext(fn)[0],
                    artist="",
                    duration=0,
                    file_path=full,
                    provider=SourceProvider.local,
                )
            )
    return results
