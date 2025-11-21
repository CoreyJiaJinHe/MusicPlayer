from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl, QTimer, QThread, QObject, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QLineEdit,
    QLabel,
    QComboBox,
    QMessageBox,
    QSplitter,
    QMenuBar,
    QDialog,
    QCheckBox,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QListWidgetItem,
    QAbstractItemView,
    QSlider,
    QGroupBox,
    QSizePolicy,
    QInputDialog,
    QMenu
)

from models import Playlist, MediaFile, OnlineMediaFile, SourceProvider
from MusicPlayer.config.loader import (
    load_config,
    get_youtube_api_key,
    save_config,
    set_youtube_api_key,
    set_soundcloud_client_id,
    get_soundcloud_client_id,
)
from MusicPlayer.playlist.manager import PlaylistManager
from MusicPlayer.player.facade import PlayerFacade
from MusicPlayer.search.local import search_local
from MusicPlayer.search.youtube import search_youtube, from_url as youtube_from_url
from MusicPlayer.search.soundcloud import search_soundcloud, from_url as sc_from_url


class ImportWorker(QObject):
    finished = Signal(list, str, str)  # items, remote_title, error

    def __init__(self, url, fetch_func):
        super().__init__()
        self.url = url
        self.fetch_func = fetch_func

    def run(self):
        # Only data fetching; no UI operations here
        try:
            items, remote_title = self.fetch_func(self.url)
            self.finished.emit(items, remote_title, "")
        except Exception as e:
            self.finished.emit([], "", str(e))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Music Player")

        self.cfg = load_config()
        self.pm = PlaylistManager()
        self.player = PlayerFacade()
        self._net = QNetworkAccessManager(self)

        # Left: Playlists
        self.playlists = QListWidget()
        self.playlists.addItems(self.pm.names)
        self.playlists.currentTextChanged.connect(self._on_playlist_selected)

        btn_new_pl = QPushButton("New Playlist")
        btn_del_pl = QPushButton("Delete Playlist")
        btn_import_pl = QPushButton("Import Playlist")
        btn_edit_pl = QPushButton("Edit Playlist")
        btn_new_pl.clicked.connect(self._create_playlist)
        btn_del_pl.clicked.connect(self._delete_playlist)
        btn_import_pl.clicked.connect(self._import_playlist)
        btn_edit_pl.clicked.connect(self._open_edit_playlist_window)

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("Playlists"))
        # Reduce playlist selection box height and width
        self.playlists.setMaximumWidth(180) # Reduced width for more space for items
        self.playlists.setMaximumHeight(120)  # Reduced height for more space for items
        left_box.addWidget(self.playlists)
        left_box.addWidget(btn_new_pl)
        left_box.addWidget(btn_del_pl)
        left_box.addWidget(btn_import_pl)
        left_box.addWidget(btn_edit_pl)
            
        # Move playlist items and actions under playlists
        self.playlist_items = QListWidget()
        self.playlist_items.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Enable multi-selection
        self.playlist_items.setDragDropMode(QAbstractItemView.InternalMove)
        self.playlist_items.itemDoubleClicked.connect(lambda _: self._play_from_playlist(self.playlist_items.currentRow()))
        self.playlist_items.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_items.customContextMenuRequested.connect(self._on_playlist_items_context_menu)
    
        self.advanced_details = False  # Advanced details toggle
        left_box.addWidget(QLabel("Playlist Items"))
        left_box.addWidget(self.playlist_items)
        actions_row = QHBoxLayout()
        btn_remove = QPushButton("Remove Selected")
        btn_save_order = QPushButton("Save Order")
        btn_remove.clicked.connect(self._remove_selected_from_playlist)
        btn_save_order.clicked.connect(self._save_playlist_order)
        actions_row.addWidget(btn_remove)
        actions_row.addWidget(btn_save_order)
        left_box.addLayout(actions_row)
        # Context menu for rename on playlists
        self.playlists.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlists.customContextMenuRequested.connect(self._on_playlists_context_menu)
        left = QWidget()
        left.setLayout(left_box)

        # Center: Search + Results
        self.source = QComboBox()
        self.source.addItems(["Local", "YouTube", "SoundCloud"])
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search title...")
        self.results = QListWidget()
        # Higher contrast on white background
        self.results.setStyleSheet("QListWidget { background: #fff; color: #222; selection-background-color: #e0e7ff; selection-color: #222; border: 1px solid #ccc; }")
        btn_search = QPushButton("Search")
        btn_add = QPushButton("Add to Playlist")
        btn_search.clicked.connect(self._do_search)
        btn_add.clicked.connect(self._add_selected_to_playlist)

        center_box = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(self.source)
        row.addWidget(self.query)
        row.addWidget(btn_search)
        center_box.addLayout(row)
        center_box.addWidget(self.results)
        center_box.addWidget(btn_add)
        center = QWidget()
        center.setLayout(center_box)

        # Right/Bottom: Player controls and view
        self.now_playing = QLabel("Now Playing: -")
        self.btn_play = QPushButton("Play Selected")
        self.btn_pause = QPushButton("Pause")
        self.btn_stop = QPushButton("Stop")
        self.btn_prev = QPushButton("Prev")
        self.btn_next = QPushButton("Next")
        self.btn_play.clicked.connect(self._play_selected)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_prev.clicked.connect(self._play_prev)
        self.btn_next.clicked.connect(self._play_next)

        controls = QHBoxLayout()
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_pause)
        controls.addWidget(self.btn_stop)
        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_next)
        # Volume
        controls.addWidget(QLabel("Vol"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.valueChanged.connect(self._on_volume_change)
        controls.addWidget(self.vol)

        right_box = QVBoxLayout()
        right_box.setAlignment(Qt.AlignTop)
        right_box.addWidget(self.now_playing)

        # Online Player area (always visible placeholder)
        self.web_group = QGroupBox("Online Player")
        self.web_group.setMinimumHeight(300)
        self.web_group_layout = QVBoxLayout(self.web_group)
        self.web_group_layout.setContentsMargins(0, 0, 0, 0)
        self.web_group_layout.setAlignment(Qt.AlignCenter)
        self.web_placeholder = QLabel("Online player will appear here when available")
        self.web_placeholder.setStyleSheet("color:#aaa; padding:8px; text-align:center;")
        self.web_group_layout.addWidget(self.web_placeholder)
        self._web_added = False
        self._right_box = right_box  # store for later

        # Try to initialize and attach web widget if available (non-fatal if it fails)
        try:
            self._attach_web_if_needed(self.web_group)
        except Exception:
            # Keep placeholder; detailed error will be shown on first playback attempt
            pass

        right_box.addWidget(self.web_group)
        right_box.addLayout(controls)
        # Playlist items and actions moved to left column
        right = QWidget()
        right.setLayout(right_box)
        self._right_container = right

        # Menu / Settings
        self._build_menubar()

        # Main splitter
        splitter = QSplitter()
        splitter.addWidget(center)  # Center column now first
        splitter.addWidget(left)    # Left column now second
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)

        root = QVBoxLayout()
        root.addWidget(splitter)
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        # Playback queue state
        self._queue_items = []  # type: ignore[var-annotated]
        self._queue_index = -1
        self.player.on_end(self._auto_advance)
        self._current_item = None  # type: ignore[var-annotated]

        # Status timer for local playback progress
        from PySide6.QtCore import QTimer
        self._status = QLabel("")
        right_box.addWidget(self._status)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._update_status)
        self._timer.start()

        # If any playlist exists, select the first to populate items immediately
        if self.playlists.count() > 0 and self.playlists.currentRow() < 0:
            self.playlists.setCurrentRow(0)

    # --- UI helpers ---
    def _build_menubar(self) -> None:
        menubar = QMenuBar(self)
        settings_menu = menubar.addMenu("Settings")

        act_music = settings_menu.addAction("Music Folder...")
        act_music.triggered.connect(self._choose_music_folder)

        act_flags = settings_menu.addAction("WebEngine Flags...")
        act_flags.triggered.connect(self._open_flags_dialog)

        act_env = settings_menu.addAction("Edit API Keys (.env)...")
        act_env.triggered.connect(self._open_env_dialog)

        # Advanced Details setting via dialog
        act_adv_details = settings_menu.addAction("Advanced Details...")
        act_adv_details.triggered.connect(self._open_advanced_details_dialog)

        self.setMenuBar(menubar)
    def _open_advanced_details_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Advanced Details Settings")
        layout = QVBoxLayout(dlg)
        cb_adv = QCheckBox("Show Advanced Details for Playlist Items")
        cb_adv.setChecked(self.advanced_details)
        layout.addWidget(cb_adv)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        def on_ok():
            self.advanced_details = cb_adv.isChecked()
            self._on_playlist_selected(self._current_playlist_name() or "")
            dlg.accept()
        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    def _open_flags_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("WebEngine Flags")
        layout = QVBoxLayout(dlg)

        # Determine current flags
        current = (self.cfg.webengine_flags or "").split()
        cb_dc = QCheckBox("Disable Direct Composition (--disable-direct-composition)")
        cb_gpu = QCheckBox("Disable GPU Acceleration (--disable-gpu)")
        cb_ap = QCheckBox("Allow Autoplay without Gesture (--autoplay-policy=no-user-gesture-required)")
        cb_dc.setChecked("--disable-direct-composition" in current or not current)
        cb_gpu.setChecked("--disable-gpu" in current)

        layout.addWidget(cb_dc)
        layout.addWidget(cb_gpu)
        layout.addWidget(cb_ap)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_save() -> None:
            flags = []
            if cb_dc.isChecked():
                flags.append("--disable-direct-composition")
            if cb_gpu.isChecked():
                flags.append("--disable-gpu")
            if cb_ap.isChecked():
                flags.append("--autoplay-policy=no-user-gesture-required")
            self.cfg.webengine_flags = " ".join(flags) if flags else None
            from MusicPlayer.config.loader import save_config

            save_config(self.cfg)
            QMessageBox.information(
                self,
                "Saved",
                "Flags saved. Please restart the application for changes to take effect.",
            )
            dlg.accept()

        buttons.accepted.connect(on_save)
        buttons.rejected.connect(dlg.reject)

        dlg.exec()

    def _on_playlist_selected(self, name: str) -> None:
        p = self.pm.get(name)
        self.playlist_items.clear()
        if not p:
            return
        if self.advanced_details:
            # Show as cards with thumbnail, title, uploader
            from PySide6.QtGui import QPixmap
            for it in p.media_files:
                w = QWidget()
                lay = QHBoxLayout(w)
                thumb = QLabel()
                thumb.setFixedSize(80, 60)
                if getattr(it, "thumbnail_url", None):
                    self._load_thumb(it.thumbnail_url, thumb)
                lay.addWidget(thumb)
                box = QVBoxLayout()
                t = QLabel(it.title)
                t.setStyleSheet("font-weight:600;color:#111")
                sub = QLabel(getattr(it, "artist", getattr(it, "uploader", "")))
                sub.setStyleSheet("color:#555")
                box.addWidget(t)
                box.addWidget(sub)
                lay.addLayout(box)
                itemw = QListWidgetItem(self.playlist_items)
                itemw.setSizeHint(w.sizeHint())
                itemw.setData(Qt.UserRole, self._item_key(it))
                self.playlist_items.addItem(itemw)
                self.playlist_items.setItemWidget(itemw, w)
        else:
            for it in p.media_files:
                itemw = QListWidgetItem(it.title)
                itemw.setData(Qt.UserRole, self._item_key(it))
                self.playlist_items.addItem(itemw)
        # Set queue to this playlist
        self._queue_items = p.media_files[:]
        self._queue_index = -1

    def _choose_music_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder", self.cfg.music_root or "")
        if folder:
            self.cfg.music_root = folder
            save_config(self.cfg)
            QMessageBox.information(self, "Saved", f"Music folder set to:\n{folder}")

    def _open_env_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("API Keys (.env)")
        layout = QVBoxLayout(dlg)

        form = QFormLayout()
        inp_yt = QLineEdit(get_youtube_api_key() or "")
        inp_sc = QLineEdit(get_soundcloud_client_id() or "")
        form.addRow("YouTube API Key", inp_yt)
        form.addRow("SoundCloud Client ID", inp_sc)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_save() -> None:
            yt = inp_yt.text().strip() or None
            sc = inp_sc.text().strip() or None
            set_youtube_api_key(yt)
            set_soundcloud_client_id(sc)
            QMessageBox.information(
                self,
                "Saved",
                ".env updated. Restart the application to load new keys.",
            )
            dlg.accept()

        buttons.accepted.connect(on_save)
        buttons.rejected.connect(dlg.reject)

        dlg.exec()

    def _current_playlist_name(self) -> Optional[str]:
        item = self.playlists.currentItem()
        return item.text() if item else None

    def _create_playlist(self) -> None:
        base = "New Playlist"
        name = base
        i = 1
        while name in self.pm.names:
            i += 1
            name = f"{base} {i}"
        self.pm.create(name)
        self.playlists.addItem(name)
        self.playlists.setCurrentRow(self.playlists.count() - 1)

    def _delete_playlist(self) -> None:
        name = self._current_playlist_name()
        if not name:
            return
        self.pm.delete(name)
        for i in range(self.playlists.count()):
            if self.playlists.item(i).text() == name:
                self.playlists.takeItem(i)
                break
        # Clear items view if deleted playlist was selected
        if self._current_playlist_name() != name:
            self.playlist_items.clear()

    def _on_playlists_context_menu(self, pos) -> None:  # noqa: ANN001
        item = self.playlists.itemAt(pos)
        if not item:
            return
        menu = QMenu(self.playlists)
        act_rename = menu.addAction("Rename...")
        chosen = menu.exec_(self.playlists.mapToGlobal(pos))
        if chosen == act_rename:
            old = item.text()
            new, ok = QInputDialog.getText(self, "Rename Playlist", "New name", QLineEdit.Normal, old)
            if ok and new.strip() and new.strip() != old:
                new = new.strip()
                if new in self.pm.names:
                    QMessageBox.warning(self, "Exists", f"Playlist '{new}' already exists.")
                    return
                try:
                    self.pm.rename(old, new)
                except Exception as e:  # pragma: no cover
                    QMessageBox.warning(self, "Error", f"Rename failed: {e}")
                    return
                item.setText(new)
                # Refresh names list order (simple approach: rebuild list widget)
                cur = new
                self.playlists.clear()
                self.playlists.addItems(self.pm.names)
                # Set current to renamed
                for i in range(self.playlists.count()):
                    if self.playlists.item(i).text() == cur:
                        self.playlists.setCurrentRow(i)
                        break

    def _import_playlist(self) -> None:
        # Non-blocking dialog to input URL and choose target playlist
        dlg = QDialog(self)
        dlg.setWindowTitle("Import Playlist")
        lay = QVBoxLayout(dlg)
        url_inp = QLineEdit()
        url_inp.setPlaceholderText("Paste YouTube or SoundCloud playlist URL...")
        lay.addWidget(QLabel("Playlist URL"))
        lay.addWidget(url_inp)
        target_box = QComboBox()
        target_box.addItem("<Create New>")
        for n in self.pm.names:
            target_box.addItem(n)
        lay.addWidget(QLabel("Import Into"))
        lay.addWidget(target_box)
        status_lbl = QLabel("")
        lay.addWidget(status_lbl)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(buttons)

        def do_import() -> None:
            url = url_inp.text().strip()
            if not url:
                QMessageBox.information(self, "URL", "Enter a playlist URL.")
                return
            buttons.setEnabled(False)
            status_lbl.setText("Importing... This may take a moment.")

            # Run fetch in background thread
            self._import_thread = QThread()
            self._import_worker = ImportWorker(url, self._fetch_playlist_url)
            self._import_worker.moveToThread(self._import_thread)
            self._import_thread.started.connect(self._import_worker.run)
            # Store dialog widgets for use in UI-thread slot
            self._import_dlg = dlg
            self._import_buttons = buttons
            self._import_status_lbl = status_lbl
            self._import_target_box = target_box
            # Cleanup and connect finished signal to a MainWindow method
            self._import_thread.finished.connect(self._import_thread.deleteLater)
            self._import_worker.finished.connect(self._import_worker.deleteLater)
            self._import_worker.finished.connect(self._on_import_finished)
            self._import_thread.start()

        buttons.accepted.connect(do_import)
        buttons.rejected.connect(dlg.reject)
        # Non-modal to keep main UI interactive
        self._import_dlg = dlg
        dlg.setModal(False)
        dlg.show()

    def _fetch_playlist_url(self, url: str):  # noqa: ANN001
        from urllib.parse import urlparse, parse_qs
        import requests
        api_key = get_youtube_api_key()
        sc_client_id = get_soundcloud_client_id()
        u = urlparse(url)
        host = u.netloc.lower()
        # Detect YouTube playlist
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
            items = []
            remote_title = None
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
                        items.append(OnlineMediaFile(title=title, artist=channel, duration=0, file_path="", provider=SourceProvider.youtube, url=f"https://www.youtube.com/watch?v={vid}", source_id=vid, thumbnail_url=thumb))
                token = data.get("nextPageToken")
                if not token:
                    break
                params["pageToken"] = token
            return items, remote_title
        # Detect SoundCloud playlist (sets)
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
            items = []
            for track in meta.get("tracks", []):
                title = track.get("title") or "(untitled)"
                artist = (track.get("user") or {}).get("username") or ""
                duration_ms = track.get("duration") or 0
                duration = int(duration_ms / 1000)
                tid = track.get("id")
                permalink = track.get("permalink_url") or ""
                thumb = (track.get("artwork_url") or "").replace("large", "t500x500") if track.get("artwork_url") else None
                items.append(OnlineMediaFile(title=title, artist=artist, duration=duration, file_path="", provider=SourceProvider.soundcloud, url=permalink, source_id=str(tid) if tid else None, thumbnail_url=thumb))
            return items, remote_title
        raise RuntimeError("Unrecognized or unsupported playlist URL.")

    def _on_import_finished(self, items, remote_title, error) -> None:  # noqa: ANN001
        # Ensure worker thread is asked to quit; do not wait here
        thr = getattr(self, "_import_thread", None)
        if thr is not None and thr.isRunning():
            try:
                thr.quit()
            except Exception:
                pass
        dlg = getattr(self, "_import_dlg", None)
        buttons = getattr(self, "_import_buttons", None)
        status_lbl = getattr(self, "_import_status_lbl", None)
        target_box = getattr(self, "_import_target_box", None)
        if not (dlg and buttons and status_lbl and target_box):
            return
        if error:
            QMessageBox.warning(self, "Import Failed", error)
            try:
                buttons.setEnabled(True)
                status_lbl.setText("")
            except Exception:
                pass
            return
        if not items:
            QMessageBox.information(self, "Empty", "No items found in playlist.")
            try:
                buttons.setEnabled(True)
                status_lbl.setText("")
            except Exception:
                pass
            return
        target = target_box.currentText()
        if target == "<Create New>":
            default_name = remote_title or "Imported Playlist"
            new_name, ok = QInputDialog.getText(self, "New Playlist Name", "Name", QLineEdit.Normal, default_name)
            if not ok or not new_name.strip():
                buttons.setEnabled(True)
                status_lbl.setText("")
                return
            new_name = new_name.strip()
            if new_name in self.pm.names:
                QMessageBox.warning(self, "Exists", f"Playlist '{new_name}' already exists.")
                buttons.setEnabled(True)
                status_lbl.setText("")
                return
            self.pm.create(new_name)
            target = new_name
            self.playlists.addItem(new_name)
        for it in items:
            self.pm.add(target, it)
        if self._current_playlist_name() == target:
            for it in items:
                itemw = QListWidgetItem(it.title)
                itemw.setData(Qt.UserRole, self._item_key(it))
                self.playlist_items.addItem(itemw)
            self._queue_items.extend(items)
        QMessageBox.information(self, "Imported", f"Imported {len(items)} items into '{target}'.")
        status_lbl.setText("Import complete.")
        try:
            dlg.accept()
        except Exception:
            pass

    def _do_search(self) -> None:
        source = self.source.currentText()
        query = self.query.text().strip()
        self.results.clear()
        if source == "Local":
            items = search_local(self.cfg.music_root, query)
        elif source == "YouTube":
            api_key = get_youtube_api_key()
            if not api_key:
                QMessageBox.information(self, "YouTube API Key", "Create a .env file and set YOUTUBE_API_KEY=... to enable YouTube search.")
                items = []
            else:
                # Detect direct URL usage
                qlow = query.lower()
                if qlow.startswith("http://") or qlow.startswith("https://"):
                    if "youtu" in qlow:
                        direct = youtube_from_url(api_key, query)
                        if direct:
                            items = [direct]
                        else:
                            QMessageBox.warning(self, "YouTube", "Could not resolve video from URL. Falling back to title search.")
                            items = search_youtube(api_key, query)
                    else:
                        # Not a YouTube URL, fallback to keyword search
                        items = search_youtube(api_key, query)
                else:
                    items = search_youtube(api_key, query)
        else:
            items = search_soundcloud(query)
        self._populate_results(items)
        # stash found items for add/play
        self._found_items = items  # type: ignore[attr-defined]

    def _add_selected_to_playlist(self) -> None:
        name = self._current_playlist_name()
        if not name:
            QMessageBox.information(self, "Playlist", "Select or create a playlist first.")
            return
        row = self.results.currentRow()
        if row < 0:
            return
        item = getattr(self, "_found_items", [])[row]
        self.pm.add(name, item)
        # If current playlist matches, update UI immediately
        cur = self._current_playlist_name()
        if cur == name:
            self.playlist_items.addItem(QListWidgetItem(item.title))
            self._queue_items.append(item)
        QMessageBox.information(self, "Added", f"Added '{item.title}' to '{name}'.")

    def _toggle_pause(self) -> None:
        # Toggle between pause and resume based on button text
        try:
            if self.btn_pause.text().lower().startswith("pause"):
                self.player.pause()
                self.btn_pause.setText("Resume")
                # Mark Now Playing as paused
                cur = self.now_playing.text()
                if cur and "[Paused]" not in cur:
                    self.now_playing.setText(f"{cur} [Paused]")
            else:
                # Resume
                self.player.resume()
                self.btn_pause.setText("Pause")
                # Remove paused marker
                self.now_playing.setText(self.now_playing.text().replace(" [Paused]", ""))
        except Exception:
            # Keep UI consistent even if underlying player errors
            if self.btn_pause.text().lower().startswith("resume"):
                self.btn_pause.setText("Pause")
            # Best-effort clean up paused marker
            self.now_playing.setText(self.now_playing.text().replace(" [Paused]", ""))

    def _on_stop_clicked(self) -> None:
        try:
            self.player.stop()
        finally:
            # Reset pause button label and remove paused marker from Now Playing
            self.btn_pause.setText("Pause")
            self.now_playing.setText(self.now_playing.text().replace(" [Paused]", ""))

    def _play_selected(self) -> None:
        # Prefer a selection in search results; fallback to playlist items
        row = self.results.currentRow()
        item = None
        if row >= 0:
            items = getattr(self, "_found_items", [])
            if items:
                item = items[row]
        else:
            prow = self.playlist_items.currentRow()
            if prow >= 0 and 0 <= prow < len(self._queue_items):
                item = self._queue_items[prow]
        if not item:
            return
        self.now_playing.setText(f"Now Playing: {item.title}")
        # Ensure web player is available and attached if needed
        from models import SourceProvider as _SP
        if getattr(item, "provider", None) in (_SP.youtube, _SP.soundcloud):
            self._attach_web_if_needed(self.web_group)
        try:
            self.player.play(item)
        except RuntimeError as e:
            QMessageBox.warning(
                self,
                "Web Player Error",
                f"Online playback failed.\n\nDetails: {e}\n\nIf this mentions Qt WebEngine, install PySide6-Addons and restart.",
            )
            return
        self._current_item = item
        # Reset pause button to Pause state when a new item starts
        self.btn_pause.setText("Pause")

    def _play_from_playlist(self, index: int) -> None:
        if index < 0 or index >= len(self._queue_items):
            return
        self._queue_index = index
        item = self._queue_items[index]
        self.now_playing.setText(f"Now Playing: {item.title}")
        # Ensure web player is available and attached if needed
        from models import SourceProvider as _SP
        if getattr(item, "provider", None) in (_SP.youtube, _SP.soundcloud):
            self._attach_web_if_needed(self.web_group)
        try:
            self.player.play(item)
        except RuntimeError as e:
            QMessageBox.warning(
                self,
                "Web Player Error",
                f"Online playback failed.\n\nDetails: {e}\n\nIf this mentions Qt WebEngine, install PySide6-Addons and restart.",
            )
            return
        self._current_item = item
        # Reset pause button to Pause state when a new item starts
        self.btn_pause.setText("Pause")

    def _on_volume_change(self, value: int) -> None:
        try:
            self.player.set_volume(int(value))
        except Exception:
            pass

    def _populate_results(self, items) -> None:  # noqa: ANN001
        from PySide6.QtGui import QPixmap
        import requests as _req
        self.results.clear()
        for it in items:
            w = QWidget()
            lay = QHBoxLayout(w)
            # Thumbnail (if any)
            thumb = QLabel()
            thumb.setFixedSize(120, 90)
            if getattr(it, "thumbnail_url", None):
                self._load_thumb(it.thumbnail_url, thumb)
            lay.addWidget(thumb)
            # Texts
            box = QVBoxLayout()
            t = QLabel(it.title)
            t.setStyleSheet("font-weight:600;color:#111")
            sub = QLabel(getattr(it, "artist", ""))
            sub.setStyleSheet("color:#555")
            box.addWidget(t)
            box.addWidget(sub)
            lay.addLayout(box)
            item = QListWidgetItem(self.results)
            item.setSizeHint(w.sizeHint())
            self.results.addItem(item)
            self.results.setItemWidget(item, w)

    def _load_thumb(self, url: str, label: QLabel) -> None:
        try:
            req = QNetworkRequest(QUrl(url))
            reply = self._net.get(req)

            def _on_finished() -> None:
                from PySide6.QtGui import QPixmap
                try:
                    data = reply.readAll()
                    pm = QPixmap()
                    if pm.loadFromData(bytes(data)):
                        label.setPixmap(pm.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                except Exception:
                    pass
                finally:
                    reply.deleteLater()

            reply.finished.connect(_on_finished)
        except Exception:
            pass

    def _item_key(self, it) -> str:  # noqa: ANN001
        prov = getattr(it, "provider", None)
        prov_val = prov.value if hasattr(prov, "value") else str(prov)
        if prov_val == "local":
            return f"{prov_val}:{getattr(it, 'file_path', '')}"
        # online
        sid = getattr(it, "source_id", None)
        url = getattr(it, "url", None)
        return f"{prov_val}:{sid or url or ''}"
    def _play_next(self) -> None:
        if not self._queue_items:
            return
        nxt = self._queue_index + 1
        if nxt < len(self._queue_items):
            self._play_from_playlist(nxt)

    def _play_prev(self) -> None:
        if not self._queue_items:
            return
        prv = self._queue_index - 1
        if prv >= 0:
            self._play_from_playlist(prv)

    def _auto_advance(self) -> None:
        # Called by player facade when a track ends (local or web)
        self._play_next()

    def _attach_web_if_needed(self, parent_widget: QWidget) -> None:  # noqa: ANN001
        # Lazily ensure the web player exists and add to the Online Player box
        try:
            created = self.player.ensure_web(parent_widget)
        except RuntimeError as e:
            # Surface the error in the placeholder for quick visibility
            if self.web_placeholder is not None:
                self.web_placeholder.setText(f"Online player unavailable. Details: {e}")
            raise
        if created and not self._web_added:
            w = self.player.web_widget()
            if w:
                # Replace placeholder with the actual web view
                if self.web_placeholder is not None:
                    self.web_group_layout.removeWidget(self.web_placeholder)
                    self.web_placeholder.setParent(None)
                    self.web_placeholder = None  # type: ignore[assignment]
                # Constrain the embedded player width and center it
                w.setMinimumSize(640, 400)
                w.setMaximumWidth(640)
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self.web_group_layout.addWidget(w, alignment=Qt.AlignCenter)
                self._web_added = True

    def _remove_selected_from_playlist(self) -> None:
        name = self._current_playlist_name()
        if not name:
            return
        selected_items = self.playlist_items.selectedItems()
        if not selected_items:
            return
        # Get selected rows, sort in reverse so we can safely remove
        rows = sorted([self.playlist_items.row(item) for item in selected_items], reverse=True)
        for row in rows:
            self.playlist_items.takeItem(row)
            self.pm.remove(name, row)
            if 0 <= row < len(self._queue_items):
                del self._queue_items[row]
        # Adjust queue index if needed
        if self._queue_index >= len(self._queue_items):
            self._queue_index = len(self._queue_items) - 1

    def _save_playlist_order(self) -> None:
        name = self._current_playlist_name()
        if not name:
            return
        # Read order from list widget and rebuild items accordingly
        keys = [self.playlist_items.item(i).data(Qt.UserRole) for i in range(self.playlist_items.count())]
        # Stable match by key order against current queue
        keymap = {self._item_key(it): it for it in self._queue_items}
        new_items = [keymap[k] for k in keys if k in keymap]
        # Persist by replacing the playlist contents
        try:
            from MusicPlayer.playlist.manager import PlaylistManager
            # Using existing manager to persist
            p = self.pm.get(name)
            if p:
                p.media_files = new_items
                self.pm._persist()  # type: ignore[attr-defined]
                self._queue_items = new_items
                QMessageBox.information(self, "Saved", "Playlist order saved.")
        except Exception:
            QMessageBox.warning(self, "Error", "Failed to save order.")

    def _update_status(self) -> None:
        # Only reliable for local playback via VLC
        if not self._current_item:
            self._status.setText("")
            return
        if getattr(self._current_item, "provider", None) != SourceProvider.local:
            self._status.setText("")
            return
        # Query VLC for time
        try:
            current_ms = self.player.local.get_time_ms()
            length_ms = self.player.local.get_length_ms()
            def fmt(ms: int) -> str:
                s = max(0, ms // 1000)
                m, s = divmod(s, 60)
                h, m = divmod(m, 60)
                return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"
            if length_ms > 0:
                self._status.setText(f"{fmt(current_ms)} / {fmt(length_ms)}")
            else:
                self._status.setText("")
        except Exception:
            self._status.setText("")

    
    def _on_playlist_items_context_menu(self, pos):
        selected = self.playlist_items.selectedItems()
        if not selected:
            return
        menu = QMenu(self.playlist_items)
        act_top = menu.addAction("Move to Top")
        act_bottom = menu.addAction("Move to Bottom")
        act_remove = menu.addAction("Remove from Playlist")
        chosen = menu.exec_(self.playlist_items.mapToGlobal(pos))
        rows = [self.playlist_items.row(item) for item in selected]
        rows.sort()
        if chosen == act_top:
            for i, row in enumerate(rows):
                item = self.playlist_items.takeItem(row - i)
                self.playlist_items.insertItem(i, item)
        elif chosen == act_bottom:
            count = self.playlist_items.count()
            for i, row in enumerate(rows[::-1]):
                item = self.playlist_items.takeItem(row)
                self.playlist_items.insertItem(count - 1, item)
        elif chosen == act_remove:
            for row in reversed(rows):
                self.playlist_items.takeItem(row)
            # Also remove from queue and playlist manager
            name = self._current_playlist_name()
            if name:
                for row in reversed(rows):
                    self.pm.remove(name, row)
                    if 0 <= row < len(self._queue_items):
                        del self._queue_items[row]
                        
    def _open_edit_playlist_window(self):
        from MusicPlayer.gui.playlist_edit_window import PlaylistEditWindow
        dlg = PlaylistEditWindow(self)
        dlg.exec()