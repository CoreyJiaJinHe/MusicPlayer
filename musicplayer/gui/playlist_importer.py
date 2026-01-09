from typing import Optional, Tuple, List
import logging
from PySide6.QtCore import QObject, Signal, QThread, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QDialogButtonBox,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
)

from models import OnlineMediaFile, SourceProvider
from MusicPlayer.config.loader import (
    get_youtube_api_key,
    get_soundcloud_client_id,
)


class ImportWorker(QObject):
    finished = Signal(list, str, str)  # items, remote_title, error

    def __init__(self, url: str, fetch_func) -> None:
        super().__init__()
        self.url = url
        self.fetch_func = fetch_func

    def run(self) -> None:
        try:
            items, remote_title = self.fetch_func(self.url)
            self.finished.emit(items, remote_title, "")
        except Exception as e:
            self.finished.emit([], "", str(e))


class PlaylistImporter:
    """Controller to handle importing playlists from YouTube/SoundCloud."""

    def __init__(self, main_window) -> None:
        self.main = main_window
        # Threading state for import operations
        self._import_thread: Optional[QThread] = None
        self._import_worker: Optional[ImportWorker] = None
        # Dialog/widget references stored during import
        self._import_dlg: Optional[QDialog] = None
        self._import_buttons: Optional[QDialogButtonBox] = None
        self._import_status_lbl: Optional[QLabel] = None
        self._import_target_box: Optional[QComboBox] = None
        self._import_append_box: Optional[QComboBox] = None

    def open_dialog(self) -> None:
        """Open the import dialog non-modally and start background import when OK."""
        dlg = QDialog(self.main)
        dlg.setWindowTitle("Import Playlist")
        lay = QVBoxLayout(dlg)
        url_inp = QLineEdit()
        url_inp.setPlaceholderText("Paste YouTube or SoundCloud playlist URL...")
        lay.addWidget(QLabel("Playlist URL"))
        lay.addWidget(url_inp)
        target_box = QComboBox()
        target_box.addItem("<Create New>")
        for n in self.main.pm.names:
            target_box.addItem(n)
        lay.addWidget(QLabel("Import Into"))
        lay.addWidget(target_box)
        append_box = QComboBox()
        append_box.addItems(["End (Append)", "Front (Prepend)"])
        lay.addWidget(QLabel("Append To"))
        lay.addWidget(append_box)
        status_lbl = QLabel("")
        lay.addWidget(status_lbl)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(buttons)

        def do_import() -> None:
            url = url_inp.text().strip()
            if not url:
                QMessageBox.information(self.main, "URL", "Enter a playlist URL.")
                return
            buttons.setEnabled(False)
            status_lbl.setText("Importing... This may take a moment.")

            self._import_thread = QThread()
            self._import_worker = ImportWorker(url, self._fetch_playlist_url)
            self._import_worker.moveToThread(self._import_thread)
            self._import_thread.started.connect(self._import_worker.run)
            # Store dialog widgets
            self._import_dlg = dlg
            self._import_buttons = buttons
            self._import_status_lbl = status_lbl
            self._import_target_box = target_box
            self._import_append_box = append_box
            # Cleanup and finished handling
            self._import_thread.finished.connect(self._import_thread.deleteLater)
            self._import_worker.finished.connect(self._import_worker.deleteLater)
            self._import_worker.finished.connect(self._on_import_finished)
            self._import_thread.start()

        buttons.accepted.connect(do_import)
        buttons.rejected.connect(dlg.reject)
        dlg.setModal(False)
        dlg.show()

    def _fetch_playlist_url(self, url: str) -> Tuple[List[OnlineMediaFile], Optional[str]]:
        from urllib.parse import urlparse, parse_qs
        import requests
        api_key = get_youtube_api_key()
        sc_client_id = get_soundcloud_client_id()
        u = urlparse(url)
        host = u.netloc.lower()
        # YouTube playlist
        if "youtube" in host or "youtu.be" in host:
            qs = parse_qs(u.query)
            playlist_id = qs.get("list", [None])[0]
            if not playlist_id:
                raise RuntimeError("Not a YouTube playlist URL (missing list parameter).")
            if not api_key:
                raise RuntimeError("YouTube API key not configured.")
            yt_api = "https://www.googleapis.com/youtube/v3/playlistItems"
            params = {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": 50,
                "key": api_key,
            }
            items: List[OnlineMediaFile] = []
            remote_title: Optional[str] = None
            while True:
                r = requests.get(yt_api, params=params, timeout=15)
                if r.status_code != 200:
                    if r.status_code in (401, 403):
                        raise RuntimeError("YouTube playlist is private or inaccessible (HTTP 403/401).")
                    raise RuntimeError(f"YouTube API error {r.status_code}: {r.text[:200]}")
                data = r.json()
                if remote_title is None:
                    remote_title = data.get("items", [{}])[0].get("snippet", {}).get("channelTitle") or "YouTube Playlist"
                for it in data.get("items", []):
                    snip = it.get("snippet", {})
                    vid = snip.get("resourceId", {}).get("videoId")
                    title = snip.get("title") or "(untitled)"
                    channel = snip.get("videoOwnerChannelTitle") or snip.get("channelTitle") or ""
                    thumb = snip.get("thumbnails", {}).get("default", {}).get("url")
                    if vid:
                        items.append(
                            OnlineMediaFile(
                                title=title,
                                artist=channel,
                                duration=0,
                                file_path="",
                                provider=SourceProvider.youtube,
                                url=f"https://www.youtube.com/watch?v={vid}",
                                source_id=vid,
                                thumbnail_url=thumb,
                            )
                        )
                token = data.get("nextPageToken")
                if not token:
                    break
                params["pageToken"] = token
            return items, remote_title
        # SoundCloud playlist (sets)
        if "soundcloud" in host:
            if not sc_client_id:
                raise RuntimeError("SoundCloud client id not configured.")
            resolve = "https://api.soundcloud.com/resolve"
            rv = requests.get(resolve, params={"url": url, "client_id": sc_client_id}, timeout=15)
            if rv.status_code != 200:
                if rv.status_code in (401, 403):
                    raise RuntimeError("SoundCloud playlist is private or inaccessible (HTTP 403/401).")
                raise RuntimeError(f"SoundCloud resolve error {rv.status_code}: {rv.text[:200]}")
            meta = rv.json()
            if meta.get("kind") != "playlist":
                raise RuntimeError("URL did not resolve to a SoundCloud playlist.")
            remote_title = meta.get("title") or "SoundCloud Playlist"
            items: List[OnlineMediaFile] = []
            for track in meta.get("tracks", []):
                title = track.get("title") or "(untitled)"
                artist = (track.get("user") or {}).get("username") or ""
                duration_ms = track.get("duration") or 0
                duration = int(duration_ms / 1000)
                tid = track.get("id")
                permalink = track.get("permalink_url") or ""
                thumb = (track.get("artwork_url") or "").replace("large", "t500x500") if track.get("artwork_url") else None
                items.append(
                    OnlineMediaFile(
                        title=title,
                        artist=artist,
                        duration=duration,
                        file_path="",
                        provider=SourceProvider.soundcloud,
                        url=permalink,
                        source_id=str(tid) if tid else None,
                        thumbnail_url=thumb,
                    )
                )
            return items, remote_title
        raise RuntimeError("Unrecognized or unsupported playlist URL.")

    def _on_import_finished(self, items, remote_title, error) -> None:  # noqa: ANN001
        thr = getattr(self, "_import_thread", None)
        if thr is not None and thr.isRunning():
            try:
                thr.quit()
            except Exception:
                pass
        dlg = self._import_dlg
        buttons = self._import_buttons
        status_lbl = self._import_status_lbl
        target_box = self._import_target_box
        if not (dlg and buttons and status_lbl and target_box):
            return
        if error:
            QMessageBox.warning(self.main, "Import Failed", error)
            try:
                buttons.setEnabled(True)
                status_lbl.setText("")
            except Exception:
                pass
            return
        if not items:
            QMessageBox.information(self.main, "Empty", "No items found in playlist.")
            try:
                buttons.setEnabled(True)
                status_lbl.setText("")
            except Exception:
                pass
            return
        target = target_box.currentText()
        append_choice = self._import_append_box.currentText() if self._import_append_box is not None else "End (Append)"
        if target == "<Create New>":
            default_name = remote_title or "Imported Playlist"
            new_name, ok = QInputDialog.getText(self.main, "New Playlist Name", "Name", QLineEdit.Normal, default_name)
            if not ok or not new_name.strip():
                buttons.setEnabled(True)
                status_lbl.setText("")
                return
            new_name = new_name.strip()
            if new_name in self.main.pm.names:
                QMessageBox.warning(self.main, "Exists", f"Playlist '{new_name}' already exists.")
                buttons.setEnabled(True)
                status_lbl.setText("")
                return
            self.main.pm.create(new_name)
            target = new_name
            self.main.playlists.addItem(new_name)
        # Persist into playlist (prepend or append)
        if append_choice.startswith("Front"):
            p = self.main.pm.get(target)
            if p:
                p.media_files = items + p.media_files
                try:
                    self.main.pm._persist()  # type: ignore[attr-defined]
                except Exception:
                    pass
        else:
            for it in items:
                self.main.pm.add(target, it)

        # Update UI and in-memory queue if current playlist is target
        if self.main._current_playlist_name() == target:
            if append_choice.startswith("Front"):
                for it in reversed(items):
                    itemw = QListWidgetItem(it.title)
                    itemw.setData(Qt.UserRole, self.main._item_key(it))
                    self.main.playlist_items.insertItem(0, itemw)
                self.main._queue_items = items + self.main._queue_items
            else:
                for it in items:
                    itemw = QListWidgetItem(it.title)
                    itemw.setData(Qt.UserRole, self.main._item_key(it))
                    self.main.playlist_items.addItem(itemw)
                self.main._queue_items.extend(items)
        QMessageBox.information(self.main, "Imported", f"Imported {len(items)} items into '{target}'.")
        status_lbl.setText("Import complete.")
        try:
            dlg.accept()
        except Exception:
            pass
        try:
            # Refresh and auto-show queue for playlist selection
            self.main.queue_controller.refresh(
                self.main._queue_items,
                self.main._queue_index,
                getattr(self.main, "_shuffled_indices", []),
                self.main.shuffle_enabled,
                self.main.auto_scroll_queue,
            )
            self.main._queue_scroll.setVisible(True)
            self.main.btn_toggle_queue.setChecked(True)
            self.main.btn_toggle_queue.setText("Hide Queue")
        except Exception:
            pass
