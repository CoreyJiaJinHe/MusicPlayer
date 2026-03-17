from typing import Optional
import re
import logging
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
    QScrollArea,
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
import logging
from MusicPlayer.search.youtube import (
    search_youtube,
    from_url as youtube_from_url,
    search_youtube_channels,
    resolve_channel_id,
    list_channel_videos,
)
from MusicPlayer.search.soundcloud import search_soundcloud, from_url as sc_from_url
from MusicPlayer.gui.channel_controller import ChannelVideosController
from MusicPlayer.gui.playlist_importer import PlaylistImporter
from MusicPlayer.gui.queue_view import QueueViewController
from MusicPlayer.gui.menu_controller import MenuController


# ImportWorker moved to playlist_importer.py


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Music Player")

        self.cfg = load_config()
        self.pm = PlaylistManager()
        self.player = PlayerFacade()
        self._net = QNetworkAccessManager(self)
        # Shuffle and loop state
        self.shuffle_enabled = False
        self.loop_enabled = True  # Loop is active by default
        self._shuffled_indices = []
        self._played_indices = set()

        # Left: Playlists
        self.playlists = QListWidget()
        self.playlists.addItems(self.pm.names)
        self.playlists.currentTextChanged.connect(self._on_playlist_selected)

        btn_new_pl = QPushButton("New Playlist")
        btn_del_pl = QPushButton("Delete Playlist")
        btn_import_pl = QPushButton("Import Playlist")
        btn_export_pl = QPushButton("Export Playlist")
        btn_edit_pl = QPushButton("Edit Playlist")
        btn_new_pl.clicked.connect(self._create_playlist)
        btn_del_pl.clicked.connect(self._delete_playlist)
        # Use PlaylistImporter controller
        self.playlist_importer = PlaylistImporter(self)
        btn_import_pl.clicked.connect(self.playlist_importer.open_dialog)
        btn_export_pl.clicked.connect(self.playlist_importer.export_selected_playlist)
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
        left_box.addWidget(btn_export_pl)
        left_box.addWidget(btn_edit_pl)
        # Preference: auto-scroll queue to current track when playback changes
        self.auto_scroll_queue = True
        # Hold references to card widgets for scrolling/highlighting
        self._queue_card_widgets = []
            
        # Playlist items: containerized so it can be shown/hidden via a toggle button
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
        # YouTube search mode: Videos vs Channels
        self.youtube_mode = QComboBox()
        self.youtube_mode.addItems(["Videos", "Channels"])
        self.youtube_mode.setVisible(False)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search title...")
        self.results = QListWidget()
        # Higher contrast on white background
        self.results.setStyleSheet("QListWidget { background: #fff; color: #222; selection-background-color: #e0e7ff; selection-color: #222; border: 1px solid #ccc; }")
        btn_search = QPushButton("Search")
        btn_add = QPushButton("Add to Playlist")
        btn_search.clicked.connect(self._do_search)
        btn_add.clicked.connect(self._add_selected_to_playlist)
        # Expose add button for enable/disable
        self.btn_add = btn_add

        center_box = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(self.source)
        row.addWidget(self.youtube_mode)
        row.addWidget(self.query)
        row.addWidget(btn_search)
        center_box.addLayout(row)
        center_box.addWidget(self.results)
        # Channel videos controls: Back / Prev / Next / Save All
        controls_row = QHBoxLayout()
        self.btn_back_channels = QPushButton("Back to Channels")
        self.btn_prev_page = QPushButton("Prev Page")
        self.btn_next_page = QPushButton("Next Page")
        self.btn_save_all = QPushButton("Save All to New Playlist")
        for b in (self.btn_back_channels, self.btn_prev_page, self.btn_next_page, self.btn_save_all):
            b.setVisible(False)
        self.btn_back_channels.clicked.connect(lambda: self.channel_controller.on_back_to_channels())
        self.btn_prev_page.clicked.connect(lambda: self.channel_controller.on_channel_prev_page())
        self.btn_next_page.clicked.connect(lambda: self.channel_controller.on_channel_next_page())
        self.btn_save_all.clicked.connect(lambda: self.channel_controller.on_save_all_results())
        controls_row.addWidget(self.btn_back_channels)
        controls_row.addStretch(1)
        controls_row.addWidget(self.btn_prev_page)
        controls_row.addWidget(self.btn_next_page)
        controls_row.addWidget(self.btn_save_all)
        center_box.addLayout(controls_row)
        center_box.addWidget(btn_add)
        center = QWidget()
        center.setLayout(center_box)
        # Toggle YouTube mode visibility based on source selection
        self.source.currentTextChanged.connect(lambda s: self.youtube_mode.setVisible(s == "YouTube"))
        # Double-click/activate on results for channel → fetch channel videos
        self.results.itemDoubleClicked.connect(lambda item: self.channel_controller.on_results_double_clicked(item))
        try:
            self.results.itemActivated.connect(lambda item: self.channel_controller.on_results_double_clicked(item))
        except Exception:
            pass

        # Initialize controller for YouTube channel browsing
        self.channel_controller = ChannelVideosController(self)

        # Right/Bottom: Player controls and view
        self.now_playing = QLabel("Now Playing: -")
        # Label to indicate which playlist/queue we're playing from
        self.play_source_label = QLabel("")
        self.play_source_label.setStyleSheet("color:#666;font-size:11px;")
        self.btn_play = QPushButton("Play Selected")
        self.btn_pause = QPushButton("Pause")
        self.btn_stop = QPushButton("Stop")
        self.btn_prev = QPushButton("Prev")
        self.btn_next = QPushButton("Next")
        self.btn_shuffle = QCheckBox("Shuffle")
        self.btn_loop = QCheckBox("Loop")
        self.btn_shuffle.setChecked(False)
        self.btn_loop.setChecked(True)
        self.btn_shuffle.stateChanged.connect(self._toggle_shuffle)
        self.btn_loop.stateChanged.connect(self._toggle_loop)
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
        controls.addWidget(self.btn_shuffle)
        controls.addWidget(self.btn_loop)
        # Volume
        controls.addWidget(QLabel("Vol"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.valueChanged.connect(self._on_volume_change)
        controls.addWidget(self.vol)

        right_box = QVBoxLayout()
        right_box.setAlignment(Qt.AlignTop)
        right_box.addWidget(self.play_source_label)
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
        # Queue toggle and horizontally-scrollable cards (hidden by default)
        self.btn_toggle_queue = QPushButton("Show Queue")
        self.btn_toggle_queue.setCheckable(True)
        # Queue toggle and auto-scroll checkbox
        qrow = QHBoxLayout()
        qrow.addWidget(self.btn_toggle_queue)
        self.chk_auto_scroll = QCheckBox("Auto-scroll")
        self.chk_auto_scroll.setChecked(self.auto_scroll_queue)
        # Toggle auto-scroll preference
        self.chk_auto_scroll.toggled.connect(lambda v: setattr(self, 'auto_scroll_queue', bool(v)))
        qrow.addWidget(self.chk_auto_scroll)
        right_box.addLayout(qrow)

        self._queue_scroll = QScrollArea()
        self._queue_scroll.setWidgetResizable(True)
        self._queue_container = QWidget()
        self._queue_layout = QHBoxLayout(self._queue_container)
        self._queue_layout.setContentsMargins(4, 4, 4, 4)
        self._queue_layout.setSpacing(8)
        self._queue_scroll.setWidget(self._queue_container)
        self._queue_scroll.setVisible(False)
        right_box.addWidget(self._queue_scroll)
        # Queue view controller
        self.queue_controller = QueueViewController(
            scroll_area=self._queue_scroll,
            layout=self._queue_layout,
            toggle_button=self.btn_toggle_queue,
            load_thumb=self._load_thumb,
        )
        self.queue_controller.set_play_handler(lambda idx: self._play_from_playlist(idx))
        self.btn_toggle_queue.clicked.connect(self.queue_controller.toggle_view)
        # Playlist items and actions moved to left column
        right = QWidget()
        right.setLayout(right_box)
        self._right_container = right

        # Menu / Settings via controller
        self.menu_controller = MenuController(self)
        self.menu_controller.attach()

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
        # Track whether Stop has been pressed (prevents monitors from acting)
        self._stopped = False
        # Track current play source: None, playlist name, or 'merged'
        self._current_play_source = None
        # Preference: deduplicate merged playlists
        self.dedupe_merged = True

        # Status timer for local playback progress
        # QTimer already imported at module level
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
    # Menu, dialogs, and unavailable view now handled by MenuController
    # Removed legacy menubar and dialog methods from MainWindow.
    def _on_playlist_selected(self, name: str) -> None:
        p = self.pm.get(name)
        self.playlist_items.clear()
        if not p:
            return
        if self.advanced_details:
            # Show as cards with thumbnail, title, uploader
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
            self._reset_shuffle()
    def _toggle_shuffle(self, state):
        self.shuffle_enabled = bool(state)
        self._reset_shuffle()
        # Refresh queue cards and show the queue when shuffle changes
        try:
            self.queue_controller.refresh(
                self._queue_items,
                self._queue_index,
                getattr(self, "_shuffled_indices", []),
                self.shuffle_enabled,
                self.auto_scroll_queue,
            )
            # auto-show queue when shuffle toggled
            self._queue_scroll.setVisible(True)
            self.btn_toggle_queue.setChecked(True)
            self.btn_toggle_queue.setText("Hide Queue")
            # Scroll to current track if enabled
            if self.auto_scroll_queue and self._queue_index >= 0:
                try:
                    self.queue_controller.scroll_to_index(
                        self._queue_items,
                        self._queue_index,
                        getattr(self, "_shuffled_indices", []),
                        self.shuffle_enabled,
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _play_card(self, index: int) -> None:
        try:
            if index < 0 or index >= len(self._queue_items):
                return
            self._queue_index = index
            self._play_from_playlist(index)
            try:
                self.queue_controller.refresh(
                    self._queue_items,
                    self._queue_index,
                    getattr(self, "_shuffled_indices", []),
                    self.shuffle_enabled,
                    self.auto_scroll_queue,
                )
            except Exception:
                pass
        except Exception:
            pass

    def _scroll_to_card(self, index: int) -> None:
        try:
            self.queue_controller.scroll_to_index(
                self._queue_items,
                index,
                getattr(self, "_shuffled_indices", []),
                self.shuffle_enabled,
            )
        except Exception:
            pass

    def _toggle_loop(self, state):
        self.loop_enabled = bool(state)

    def _reset_shuffle(self):
        # Reset shuffle state when playlist changes or shuffle toggled
        self._played_indices = set()
        if self.shuffle_enabled and self._queue_items:
            import random
            self._shuffled_indices = list(range(len(self._queue_items)))
            random.shuffle(self._shuffled_indices)
        else:
            self._shuffled_indices = []

    def _choose_music_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder", self.cfg.music_root or "")
        if folder:
            self.cfg.music_root = folder
            save_config(self.cfg)
            QMessageBox.information(self, "Saved", f"Music folder set to:\n{folder}")

    # _open_env_dialog moved to MenuController

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
        # Allow actions even when right-clicking empty area: Play Combined, Play Combined (Shuffle), Rename
        item = self.playlists.itemAt(pos)
        menu = QMenu(self.playlists)
        act_play_combined = menu.addAction("Play Combined...")
        act_play_combined_shuffle = menu.addAction("Play Combined (Shuffle)")
        act_rename = menu.addAction("Rename...")
        chosen = menu.exec_(self.playlists.mapToGlobal(pos))
        if chosen == act_rename:
            # Rename only when clicking on a specific playlist
            if not item:
                return
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
        elif chosen == act_play_combined or chosen == act_play_combined_shuffle:
            shuffle = chosen == act_play_combined_shuffle
            self._open_play_combined_dialog(shuffle)
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

    # Import playlist handled by PlaylistImporter controller
    
    def _do_search(self) -> None:
        source = self.source.currentText()
        query = self.query.text().strip()
        self.results.clear()
        # Any new search resets channel videos context
        try:
            self.channel_controller.reset_for_new_search()
        except Exception:
            pass
        if source == "Local":
            items = search_local(self.cfg.music_root, query)
        elif source == "YouTube":
            api_key = get_youtube_api_key()
            if not api_key:
                QMessageBox.information(self, "YouTube API Key", "Create a .env file and set YOUTUBE_API_KEY=... to enable YouTube search.")
                items = []
            else:
                mode = self.youtube_mode.currentText() if self.youtube_mode.isVisible() else "Videos"
                qlow = query.lower()
                if mode == "Channels":
                    # If user provided a channel URL or ID/handle, resolve and list videos directly
                    cid = resolve_channel_id(api_key, query)
                    if cid:
                        self.channel_controller.enter_channel_videos(cid, query)
                        return
                    # Otherwise, perform a channel search
                    logging.warning("YouTube channel search query='%s'", query)
                    channels = search_youtube_channels(api_key, query, max_results=10)
                    logging.warning("YouTube channel search results=%d", len(channels))
                    self._found_channels = channels  # type: ignore[attr-defined]
                    self.channel_controller.populate_channel_results(channels)
                    return
                else:
                    # Videos mode (strict): only allow video titles or direct video URLs.
                    # Block channel identifiers (URLs, bare @handles, bare UC channel IDs).
                    if qlow.startswith("http://") or qlow.startswith("https://"):
                        # If a YouTube channel URL is provided, inform user to use Channels mode
                        if "youtu" in qlow and ("/channel/" in qlow or "/@" in qlow):
                            QMessageBox.information(
                                self,
                                "YouTube",
                                "Videos mode expects video titles or video URLs.\n"
                                "To browse a channel URL, switch to 'Channels' mode."
                            )
                            return
                        # Otherwise treat as possible direct video URL
                        if "youtu" in qlow:
                            direct = youtube_from_url(api_key, query)
                            if direct:
                                items = [direct]
                            else:
                                QMessageBox.warning(self, "YouTube", "Could not resolve video from URL. Falling back to title search.")
                                items = search_youtube(api_key, query)
                        else:
                            items = search_youtube(api_key, query)
                    else:
                        # Block bare channel handle (@name) and bare channel ID (UCxxxxxxxxxxxxxxxxxxxxxx)
                        qstr = query.strip()
                        is_bare_handle = bool(re.fullmatch(r"@[A-Za-z0-9._-]+", qstr))
                        is_bare_channel_id = bool(re.fullmatch(r"UC[a-zA-Z0-9_-]{22}", qstr))
                        if is_bare_handle or is_bare_channel_id:
                            QMessageBox.information(
                                self,
                                "YouTube",
                                "Videos mode expects video titles or video URLs.\n"
                                "To browse a channel identifier, switch to 'Channels' mode."
                            )
                            return
                        # Treat everything else as a title search (do NOT resolve bare video IDs)
                        items = search_youtube(api_key, query)
        else:
            items = search_soundcloud(query)
        self._populate_results(items)
        # stash found items for add/play
        self._found_items = items  # type: ignore[attr-defined]
        # For general results (not in channel videos view), hide channel controls
        try:
            self.btn_add.setEnabled(True)
            self.btn_back_channels.setVisible(False)
            self.btn_prev_page.setVisible(False)
            self.btn_next_page.setVisible(False)
            self.btn_save_all.setVisible(False)
        except Exception:
            pass

    

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
                # Clear stopped when resuming playback and remove paused marker
                try:
                    self._stopped = False
                except Exception:
                    pass
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
            # Mark stopped so monitors don't mistake this for playing
            try:
                self._stopped = True
            except Exception:
                pass
            # Reset pause button label and remove paused marker from Now Playing
            self.btn_pause.setText("Pause")
            self.now_playing.setText(self.now_playing.text().replace(" [Paused]", ""))
            # Clear play source label when stopped
            try:
                self.play_source_label.setText("")
            except Exception:
                pass

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
        # Skip if marked as unavailable and show message
        if getattr(item, "unavailable", False):
            QMessageBox.information(self, "Unavailable", f"'{item.title}' is marked as unavailable and cannot be played.")
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
        # Clear stopped flag when starting playback
        try:
            self._stopped = False
        except Exception:
            pass
        # Reset pause button to Pause state when a new item starts
        self.btn_pause.setText("Pause")
        # Update play source label and internal source state
        try:
            prow = getattr(self, 'playlist_items').currentRow()
            if prow >= 0 and prow < len(self._queue_items):
                src = self._current_playlist_name() or ""
                self._current_play_source = src or None
                if src:
                    self.play_source_label.setText(f"Playing from: {src}")
                else:
                    self.play_source_label.setText("")
            else:
                # Playing from search result or direct add
                self._current_play_source = None
                self.play_source_label.setText("")
        except Exception:
            self._current_play_source = None
            try:
                self.play_source_label.setText("")
            except Exception:
                pass
        # Refresh queue cards to reflect current queue
        try:
            self._refresh_queue_cards()
        except Exception:
            pass

    def _play_from_playlist(self, index: int) -> None:
        if index < 0 or index >= len(self._queue_items):
            return
        self._queue_index = index
        item = self._queue_items[index]
        # Skip if marked as unavailable
        if getattr(item, "unavailable", False):
            self._play_next()
            return
        self.now_playing.setText(f"Now Playing: {item.title}")
        from models import SourceProvider as _SP
        if getattr(item, "provider", None) == _SP.youtube:
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
            self.btn_pause.setText("Pause")
            # Clear stopped flag when starting playback
            try:
                self._stopped = False
            except Exception:
                pass
            # Refresh queue cards to show updated current/previous coloring
            try:
                self._refresh_queue_cards()
            except Exception:
                pass
            # Update play source label to the current playlist name unless we're in merged mode
            try:
                if getattr(self, '_current_play_source', None) != 'merged':
                    src = self._current_playlist_name() or ""
                    self._current_play_source = src or None
                    if src:
                        self.play_source_label.setText(f"Playing from: {src}")
                    else:
                        self.play_source_label.setText("")
            except Exception:
                pass
            # --- YouTube playback check ---
            web_widget = self.player.web_widget()
            if web_widget:
                def check_youtube_playback():
                    # getPlayerState: 1=playing, 2=paused, 0=ended, 5=video cued
                    js = "try { ytPlayer.getPlayerState(); } catch(e) { -1; }"
                    web_widget.page().runJavaScript(js, lambda state: self._handle_youtube_playback_state(state, index))
                QTimer.singleShot(8000, check_youtube_playback)
        else:
            # SoundCloud or local
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
            self.btn_pause.setText("Pause")
            # Refresh queue cards to show the queue for this playlist
            try:
                self._refresh_queue_cards()
            except Exception:
                pass

    def _handle_youtube_playback_state(self, state, index):
        # Only skip if still on the same song
        if index != self._queue_index:
            return
        # 1 = playing, 2 = paused, 0 = ended, 5 = video cued, -1 = error
        logging.warning("YouTube playback state: %s", state)
        if state != 1 and state != 2 :  # not playing or paused
            item = self._queue_items[index]
            item.unavailable = True
            # Persist change to playlist.json
            name = self._current_playlist_name()
            if name:
                p = self.pm.get(name)
                if p:
                    # Find and update the matching item in the playlist
                    for mf in p.media_files:
                        if getattr(mf, "source_id", None) == getattr(item, "source_id", None):
                            mf.unavailable = True
                    self.pm._persist()
            self._play_next()
            
    def _on_volume_change(self, value: int) -> None:
        try:
            self.player.set_volume(int(value))
        except Exception:
            pass

    def _populate_results(self, items) -> None:  # noqa: ANN001
        self.results.clear()
        for it in items or []:
            w = QWidget()
            lay = QHBoxLayout(w)
            # Thumbnail (if any)
            thumb = QLabel()
            thumb.setFixedSize(120, 72)
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setStyleSheet("background:transparent;")
            if getattr(it, "thumbnail_url", None):
                try:
                    self._load_thumb(it.thumbnail_url, thumb)
                except Exception:
                    pass
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
            itemw = QListWidgetItem(self.results)
            itemw.setSizeHint(w.sizeHint())
            self.results.addItem(itemw)
            self.results.setItemWidget(itemw, w)

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
                            # Scale to the target label size to avoid padding/letterbox artifacts
                            try:
                                w = label.width() or 120
                                h = label.height() or 90
                            except Exception:
                                w, h = 120, 90
                            label.setPixmap(pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
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
        if self.shuffle_enabled:
            # Play next unplayed shuffled index, skipping unavailable items
            if len(self._played_indices) == len(self._queue_items):
                # All played, reset for next round
                self._played_indices = set()
                import random
                self._shuffled_indices = list(range(len(self._queue_items)))
                random.shuffle(self._shuffled_indices)
            for idx in self._shuffled_indices:
                if idx not in self._played_indices:
                    # Skip unavailable tracks
                    if getattr(self._queue_items[idx], "unavailable", False):
                        self._played_indices.add(idx)
                        continue
                    self._played_indices.add(idx)
                    self._queue_index = idx
                    self._play_from_playlist(idx)
                    return
            # If nothing found, do nothing
        else:
            nxt = self._queue_index + 1
            # Skip unavailable tracks in sequential mode
            while nxt < len(self._queue_items) and getattr(self._queue_items[nxt], "unavailable", False):
                nxt += 1
            if nxt < len(self._queue_items):
                self._play_from_playlist(nxt)
            elif self.loop_enabled and self._queue_items:
                # Loop to start, but skip unavailable tracks
                nxt = 0
                while nxt < len(self._queue_items) and getattr(self._queue_items[nxt], "unavailable", False):
                    nxt += 1
                if nxt < len(self._queue_items):
                    self._queue_index = nxt
                    self._play_from_playlist(nxt)

    def _play_prev(self) -> None:
        if not self._queue_items:
            return
        if self.shuffle_enabled:
            # Play previous in shuffled order (if possible)
            played = [idx for idx in self._shuffled_indices if idx in self._played_indices]
            if played:
                cur_idx = played.index(self._queue_index) if self._queue_index in played else -1
                if cur_idx > 0:
                    prev_idx = played[cur_idx - 1]
                    self._queue_index = prev_idx
                    self._play_from_playlist(prev_idx)
        else:
            prv = self._queue_index - 1
            if prv >= 0:
                self._play_from_playlist(prv)

    def _auto_advance(self) -> None:
        # Called by player facade when a track ends (local or web)
        if self.shuffle_enabled:
            self._play_next()
        else:
            nxt = self._queue_index + 1
            if nxt < len(self._queue_items):
                self._play_from_playlist(nxt)
            elif self.loop_enabled and self._queue_items:
                self._queue_index = 0
                self._play_from_playlist(0)

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

    def _toggle_queue_view(self) -> None:
        try:
            self.queue_controller.toggle_view()
        except Exception:
            pass

    def _refresh_queue_cards(self) -> None:
        try:
            self.queue_controller.refresh(
                self._queue_items,
                self._queue_index,
                getattr(self, "_shuffled_indices", []),
                self.shuffle_enabled,
                self.auto_scroll_queue,
            )
        except Exception:
            pass

    
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

    def _open_play_combined_dialog(self, shuffle: bool = False) -> None:
        """Open a dialog to let the user pick multiple playlists to play together."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Play Combined Playlists")
        layout = QVBoxLayout(dlg)

        lbl = QLabel("Select playlists to combine into a single queue:")
        layout.addWidget(lbl)

        lw = QListWidget()
        lw.setSelectionMode(QAbstractItemView.MultiSelection)
        for name in self.pm.names:
            item = QListWidgetItem(name)
            lw.addItem(item)
        layout.addWidget(lw)

        cb_shuffle = QCheckBox("Shuffle combined queue")
        cb_shuffle.setChecked(shuffle)
        layout.addWidget(cb_shuffle)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_ok() -> None:
            sel = [lw.item(i).text() for i in range(lw.count()) if lw.item(i).isSelected()]
            dlg.accept()
            if not sel:
                return
            self._play_multiple_playlists(sel, cb_shuffle.isChecked())

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    def _play_multiple_playlists(self, playlist_names, shuffle: bool = False) -> None:
        """Merge the specified playlists into the current queue and begin playback.

        This replaces the current queue with the concatenation of the named playlists
        and optionally starts in shuffle mode across the combined queue.
        """
        combined = []
        for name in playlist_names:
            p = self.pm.get(name)
            if not p:
                continue
            combined.extend(p.media_files)

        # Deduplicate while preserving order (by item key) if preference enabled
        if getattr(self, 'dedupe_merged', True):
            seen = set()
            unique = []
            for it in combined:
                key = self._item_key(it)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(it)
            combined = unique

        if not combined:
            QMessageBox.information(self, "No Items", "No media files found in the selected playlists.")
            return

        # Replace the in-memory playback queue (do NOT modify stored playlists or the
        # left-hand `playlist_items` view). This keeps the original playlists intact.
        self._queue_items = combined
        self._queue_index = -1

        # Apply shuffle mode if requested (this affects only playback order)
        try:
            self.shuffle_enabled = bool(shuffle)
            self._reset_shuffle()
        except Exception:
            self.shuffle_enabled = False
            self._reset_shuffle()

        # Indicate merged playlist source
        try:
            self._current_play_source = 'merged'
            # Show which playlists are included as a small hint
            try:
                names_str = " + ".join(playlist_names)
            except Exception:
                names_str = "Merged Playlist"
            label = f"Playing combined: {names_str}"
            if shuffle:
                label += " (shuffled)"
            self.play_source_label.setText(label)
        except Exception:
            pass

        # Refresh cards and start playback from the combined queue
        try:
            self._refresh_queue_cards()
        except Exception:
            pass
        self._play_next()