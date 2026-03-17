from typing import Optional, Tuple, List
import json
from collections import Counter

from PySide6.QtCore import QObject, Signal, QThread, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QDialogButtonBox,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
    QFileDialog,
)

from models import OnlineMediaFile, SourceProvider
from MusicPlayer.config.loader import (
    get_youtube_api_key,
    get_soundcloud_client_id,
)
from MusicPlayer.playlist.storage import dict_to_playlist, playlist_to_dict


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


class PlaylistImporter(QObject):
    """Controller to handle import/export/sync for playlists."""

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.main = main_window
        # Threading state for URL import operations
        self._import_thread: Optional[QThread] = None
        self._import_worker: Optional[ImportWorker] = None
        # Dialog/widget references stored during import
        self._import_dlg: Optional[QDialog] = None
        self._import_buttons: Optional[QDialogButtonBox] = None
        self._import_status_lbl: Optional[QLabel] = None
        self._import_target_box: Optional[QComboBox] = None
        self._import_append_box: Optional[QComboBox] = None
        self._pending_import_url: Optional[str] = None

        # Threading state for sync operations
        self._sync_thread: Optional[QThread] = None
        self._sync_worker: Optional[ImportWorker] = None
        self._sync_playlist_name: Optional[str] = None
        self._sync_additions_only: bool = False
        self._sync_done_callback = None

    def open_dialog(self) -> None:
        """Open the import dialog and branch to URL/file import based on mode."""
        dlg = QDialog(self.main)
        dlg.setWindowTitle("Import Playlist")
        lay = QVBoxLayout(dlg)

        mode_box = QComboBox()
        mode_box.addItems(["From URL", "From JSON File"])
        lay.addWidget(QLabel("Import Mode"))
        lay.addWidget(mode_box)

        url_lbl = QLabel("Playlist URL")
        url_inp = QLineEdit()
        url_inp.setPlaceholderText("Paste YouTube or SoundCloud playlist URL...")
        lay.addWidget(url_lbl)
        lay.addWidget(url_inp)

        file_lbl = QLabel("JSON File")
        file_row = QHBoxLayout()
        file_inp = QLineEdit()
        file_inp.setPlaceholderText("Choose exported playlist JSON...")
        btn_browse = QPushButton("Browse...")
        file_row.addWidget(file_inp)
        file_row.addWidget(btn_browse)
        lay.addWidget(file_lbl)
        lay.addLayout(file_row)

        target_lbl = QLabel("Import Into")
        target_box = QComboBox()
        target_box.addItem("<Create New>")
        for n in self.main.pm.names:
            target_box.addItem(n)
        lay.addWidget(target_lbl)
        lay.addWidget(target_box)

        append_lbl = QLabel("Append To")
        append_box = QComboBox()
        append_box.addItems(["End (Append)", "Front (Prepend)"])
        lay.addWidget(append_lbl)
        lay.addWidget(append_box)

        status_lbl = QLabel("")
        lay.addWidget(status_lbl)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(buttons)

        def _pick_file() -> None:
            path, _ = QFileDialog.getOpenFileName(
                self.main,
                "Select Playlist JSON",
                "",
                "JSON Files (*.json)",
            )
            if path:
                file_inp.setText(path)

        def _toggle_mode() -> None:
            from_url = mode_box.currentText() == "From URL"
            url_lbl.setVisible(from_url)
            url_inp.setVisible(from_url)
            target_lbl.setVisible(from_url)
            target_box.setVisible(from_url)
            append_lbl.setVisible(from_url)
            append_box.setVisible(from_url)

            file_lbl.setVisible(not from_url)
            file_inp.setVisible(not from_url)
            btn_browse.setVisible(not from_url)

        btn_browse.clicked.connect(_pick_file)
        mode_box.currentTextChanged.connect(lambda _: _toggle_mode())
        _toggle_mode()

        def do_import() -> None:
            if mode_box.currentText() == "From URL":
                url = url_inp.text().strip()
                if not url:
                    QMessageBox.information(self.main, "URL", "Enter a playlist URL.")
                    return
                self._start_url_import(url, dlg, buttons, status_lbl, target_box, append_box)
                return

            file_path = file_inp.text().strip()
            if not file_path:
                QMessageBox.information(self.main, "File", "Select a playlist JSON file.")
                return
            self._import_from_json_file(file_path)
            try:
                dlg.accept()
            except Exception:
                pass

        buttons.accepted.connect(do_import)
        buttons.rejected.connect(dlg.reject)
        dlg.setModal(False)
        dlg.show()

    def _start_url_import(
        self,
        url: str,
        dlg: QDialog,
        buttons: QDialogButtonBox,
        status_lbl: QLabel,
        target_box: QComboBox,
        append_box: QComboBox,
    ) -> None:
        buttons.setEnabled(False)
        status_lbl.setText("Importing... This may take a moment.")
        self._pending_import_url = url

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

    def _import_from_json_file(self, file_path: str) -> None:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            QMessageBox.warning(self.main, "Import Failed", f"Could not read JSON file:\n{e}")
            return

        if isinstance(payload, dict) and isinstance(payload.get("playlist"), dict):
            payload = payload["playlist"]
        if isinstance(payload, list):
            if not payload:
                QMessageBox.information(self.main, "Import", "The JSON file is empty.")
                return
            payload = payload[0]
        if not isinstance(payload, dict):
            QMessageBox.warning(self.main, "Import Failed", "Unsupported JSON format.")
            return

        playlist = dict_to_playlist(payload)
        if not playlist.media_files:
            QMessageBox.information(self.main, "Import", "No items found in JSON playlist.")
            return

        default_name = (playlist.name or "Imported Playlist").strip() or "Imported Playlist"
        target_name = self._ask_import_name(default_name)
        if not target_name:
            return

        while target_name in self.main.pm.names:
            QMessageBox.warning(self.main, "Exists", f"Playlist '{target_name}' already exists. Choose a different name.")
            target_name = self._ask_import_name(f"{target_name} (Imported)")
            if not target_name:
                return

        self.main.pm.create(target_name, source_url=playlist.source_url)
        self.main.pm.replace_items(target_name, playlist.media_files)
        self.main.playlists.addItem(target_name)

        for i in range(self.main.playlists.count()):
            if self.main.playlists.item(i).text() == target_name:
                self.main.playlists.setCurrentRow(i)
                break

        QMessageBox.information(
            self.main,
            "Imported",
            f"Imported {len(playlist.media_files)} items into '{target_name}'.",
        )

    def _ask_import_name(self, existing_name: str) -> Optional[str]:
        msg = QMessageBox(self.main)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("Import Playlist Name")
        msg.setText(f"Use existing name from file?\n\n{existing_name}")
        btn_existing = msg.addButton("Use Existing Name", QMessageBox.AcceptRole)
        btn_custom = msg.addButton("Use Different Name", QMessageBox.ActionRole)
        btn_cancel = msg.addButton(QMessageBox.Cancel)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_cancel:
            return None
        if clicked == btn_existing:
            return existing_name

        new_name, ok = QInputDialog.getText(
            self.main,
            "Import Playlist Name",
            "Playlist name",
            QLineEdit.Normal,
            existing_name,
        )
        if not ok or not new_name.strip():
            return None
        return new_name.strip()

    def export_selected_playlist(self) -> None:
        playlist_name = self.main._current_playlist_name()
        if not playlist_name:
            QMessageBox.information(self.main, "Export", "Select a playlist first.")
            return
        playlist = self.main.pm.get(playlist_name)
        if not playlist:
            QMessageBox.warning(self.main, "Export", "Selected playlist could not be found.")
            return

        default_file = f"{playlist_name}.json"
        path, _ = QFileDialog.getSaveFileName(
            self.main,
            "Export Playlist JSON",
            default_file,
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(playlist_to_dict(playlist), f, indent=2)
            QMessageBox.information(self.main, "Export", f"Exported playlist to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self.main, "Export Failed", f"Could not export playlist:\n{e}")

    def sync_selected_playlist(self, additions_only: bool) -> None:
        playlist_name = self.main._current_playlist_name()
        self.sync_playlist(playlist_name, additions_only)

    def sync_playlist(self, playlist_name: Optional[str], additions_only: bool, on_done=None) -> None:
        if not playlist_name:
            QMessageBox.information(self.main, "Sync", "Select a playlist first.")
            return

        playlist = self.main.pm.get(playlist_name)
        if not playlist:
            QMessageBox.warning(self.main, "Sync", "Selected playlist could not be found.")
            return

        source_url = (playlist.source_url or "").strip()
        if not source_url:
            QMessageBox.information(
                self.main,
                "Sync Unavailable",
                "This playlist has no saved source URL. Import from URL first to enable sync.",
            )
            return

        if self._sync_thread is not None and self._sync_thread.isRunning():
            QMessageBox.information(self.main, "Sync", "A sync operation is already in progress.")
            return

        self._sync_playlist_name = playlist_name
        self._sync_additions_only = additions_only
        self._sync_done_callback = on_done

        self._sync_thread = QThread()
        self._sync_worker = ImportWorker(source_url, self._fetch_playlist_url)
        self._sync_worker.moveToThread(self._sync_thread)
        self._sync_thread.started.connect(self._sync_worker.run)
        self._sync_thread.finished.connect(self._sync_thread.deleteLater)
        self._sync_worker.finished.connect(self._sync_worker.deleteLater)
        self._sync_worker.finished.connect(self._on_sync_finished)
        self._sync_thread.start()

    def _on_sync_finished(self, remote_items, _remote_title, error) -> None:  # noqa: ANN001
        thr = getattr(self, "_sync_thread", None)
        if thr is not None and thr.isRunning():
            try:
                thr.quit()
            except Exception:
                pass

        playlist_name = self._sync_playlist_name
        if not playlist_name:
            return

        if error:
            QMessageBox.warning(self.main, "Sync Failed", error)
            if callable(self._sync_done_callback):
                try:
                    self._sync_done_callback(False)
                except Exception:
                    pass
            self._sync_done_callback = None
            return

        playlist = self.main.pm.get(playlist_name)
        if not playlist:
            if callable(self._sync_done_callback):
                try:
                    self._sync_done_callback(False)
                except Exception:
                    pass
            self._sync_done_callback = None
            return

        existing_items = list(playlist.media_files)
        existing_keys = [self.main._item_key(it) for it in existing_items]
        remote_keys = [self.main._item_key(it) for it in remote_items]

        if self._sync_additions_only:
            have = set(existing_keys)
            to_add = [it for it in remote_items if self.main._item_key(it) not in have]
            if to_add:
                self.main.pm.replace_items(playlist_name, existing_items + to_add)
            added_count = len(to_add)
            removed_count = 0
        else:
            self.main.pm.replace_items(playlist_name, remote_items)
            old_counter = Counter(existing_keys)
            new_counter = Counter(remote_keys)
            added_count = sum(max(new_counter[k] - old_counter[k], 0) for k in new_counter.keys())
            removed_count = sum(max(old_counter[k] - new_counter[k], 0) for k in old_counter.keys())

        if self.main._current_playlist_name() == playlist_name:
            self.main._on_playlist_selected(playlist_name)

        mode_text = "additions only" if self._sync_additions_only else "full"
        QMessageBox.information(
            self.main,
            "Playlist Synced",
            f"Completed {mode_text} sync for '{playlist_name}'.\nAdded: {added_count}\nRemoved: {removed_count}",
        )
        if callable(self._sync_done_callback):
            try:
                self._sync_done_callback(True)
            except Exception:
                pass
        self._sync_done_callback = None

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
            self.main.pm.create(new_name, source_url=self._pending_import_url)
            target = new_name
            self.main.playlists.addItem(new_name)
        else:
            # Keep imported URL metadata for future sync on existing target playlists too.
            self.main.pm.set_source_url(target, self._pending_import_url)

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
