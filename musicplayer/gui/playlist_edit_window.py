from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QLabel, QComboBox, QSplitter, QAbstractItemView, QMenu, QMessageBox, QWidget, QListWidgetItem, QCheckBox, QSizePolicy, QStyledItemDelegate, QStyle, QSpinBox, QDialogButtonBox, QFormLayout, QMenuBar
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtCore import QUrl
from PySide6.QtCore import Qt, QSettings, QTimer, QSize, QRect
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut, QPainter, QColor, QFont
from MusicPlayer.playlist.manager import PlaylistManager
from collections import OrderedDict

# Thumbnail and row sizing (keep "card" look consistently)
THUMB_SIZE = QSize(80, 60)
ROW_HEIGHT = 80
TEXT_ONLY_ROW_HEIGHT = 30

# Roles for storing thumbnail metadata
THUMB_URL_ROLE = Qt.UserRole + 1
THUMB_LOADED_ROLE = Qt.UserRole + 2

class ThumbnailLoader:
    def __init__(self, net_manager, parent=None, max_concurrency=12, cache_enabled=True, cache_max_items=1500):
        self._net = net_manager
        self._parent = parent
        self._max = max_concurrency
        self._active = 0
        self._queue = []
        self._pending = set()
        self._cache_enabled = cache_enabled
        self._cache_max = cache_max_items
        self._cache = OrderedDict()

    def set_cache_enabled(self, enabled: bool):
        self._cache_enabled = bool(enabled)

    def set_cache_max_items(self, n: int):
        self._cache_max = max(0, int(n))
        self._cache_trim()

    def _cache_get(self, url):
        if not self._cache_enabled:
            return None
        pm = self._cache.get(url)
        if pm is not None:
            self._cache.move_to_end(url)
        return pm

    def _cache_put(self, url, pm):
        if not self._cache_enabled:
            return
        self._cache[url] = pm
        self._cache.move_to_end(url)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    def _cache_trim(self):
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    def request_label(self, url, item, label, size=(80, 60)):
        pm = self._cache_get(url)
        if pm is not None:
            try:
                from PySide6.QtGui import QPixmap
                label.setPixmap(pm.scaled(size[0], size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation))
                item.setData(THUMB_LOADED_ROLE, True)
            except Exception:
                pass
            return
        self._enqueue({"url": url, "mode": "label", "item": item, "label": label, "size": size})

    def request_icon(self, url, item, size=(80, 60)):
        pm = self._cache_get(url)
        if pm is not None:
            try:
                from PySide6.QtGui import QIcon
                item.setIcon(QIcon(pm.scaled(size[0], size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                item.setData(THUMB_LOADED_ROLE, True)
            except Exception:
                pass
            return
        self._enqueue({"url": url, "mode": "icon", "item": item, "size": size})

    def request_cache(self, url, item):
        # Prefetch into cache and mark as loaded (delegate will paint)
        pm = self._cache_get(url)
        if pm is not None:
            try:
                item.setData(THUMB_LOADED_ROLE, True)
            except Exception:
                pass
            return
        self._enqueue({"url": url, "mode": "cache", "item": item})

    def get_cached_pixmap(self, url):
        return self._cache_get(url)

    def _enqueue(self, req):
        url = req["url"]
        if url in self._pending:
            return
        self._queue.append(req)
        self._pending.add(url)
        self._pump()

    def _pump(self):
        while self._active < self._max and self._queue:
            req = self._queue.pop(0)
            self._start(req)

    def _start(self, req):
        self._active += 1
        try:
            qreq = QNetworkRequest(QUrl(req["url"]))
            reply = self._net.get(qreq)
            def _on_finished():
                try:
                    data = reply.readAll()
                    from PySide6.QtGui import QPixmap, QIcon
                    pm = QPixmap()
                    ok = pm.loadFromData(bytes(data))
                    if ok:
                        self._cache_put(req["url"], pm)
                        if req["mode"] == "label":
                            label = req.get("label")
                            if label is not None:
                                label.setPixmap(pm.scaled(req["size"][0], req["size"][1], Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        elif req["mode"] == "icon":
                            item = req["item"]
                            if item is not None:
                                item.setIcon(QIcon(pm.scaled(req["size"][0], req["size"][1], Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                        # 'cache' mode: do nothing visible here
                        # for 'cache' mode we only cache and mark loaded
                        item = req.get("item")
                        if item is not None:
                            item.setData(THUMB_LOADED_ROLE, True)
                except Exception:
                    pass
                finally:
                    try:
                        reply.deleteLater()
                    except Exception:
                        pass
                    self._active -= 1
                    self._pending.discard(req["url"])
                    self._pump()
            reply.finished.connect(_on_finished)
        except Exception:
            self._active -= 1
            self._pending.discard(req["url"])
            self._pump()


class PlaylistItemDelegate(QStyledItemDelegate):
    def __init__(self, loader: ThumbnailLoader, parent=None):
        super().__init__(parent)
        self._loader = loader
        self._text_only = False

    def set_text_only(self, enabled: bool):
        self._text_only = bool(enabled)

    def paint(self, painter: QPainter, option, index):
        # Background/selection
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())

        rect = option.rect
        margin = 6
        if self._text_only:
            text_left = rect.left() + margin
            title_rect = QRect(text_left, rect.top() + 4, rect.width() - (text_left - rect.left()) - 10, 16)
            sub_rect = QRect(text_left, rect.top() + 18, rect.width() - (text_left - rect.left()) - 10, 12)
        else:
            thumb_rect = QRect(rect.left() + margin, rect.top() + (ROW_HEIGHT - THUMB_SIZE.height()) // 2, THUMB_SIZE.width(), THUMB_SIZE.height())
            text_left = thumb_rect.right() + 8
            title_rect = QRect(text_left, rect.top() + 10, rect.width() - (text_left - rect.left()) - 10, 20)
            sub_rect = QRect(text_left, rect.top() + 32, rect.width() - (text_left - rect.left()) - 10, 18)

        # Draw thumbnail or placeholder
        if not self._text_only:
            url = index.data(THUMB_URL_ROLE)
            pm = None
            if url:
                pm = self._loader.get_cached_pixmap(url)
            if pm is not None and not pm.isNull():
                scaled = pm.scaled(THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawPixmap(thumb_rect, scaled)
            else:
                painter.fillRect(thumb_rect, QColor('#e5e7eb'))
                painter.setPen(QColor('#cbd5e1'))
                painter.drawRect(thumb_rect)
            # restore pen for text
            if option.state & QStyle.State_Selected:
                painter.setPen(option.palette.highlightedText().color())
            else:
                painter.setPen(option.palette.text().color())

        # Draw title and subtitle
        title = index.data(Qt.DisplayRole) or ""
        # If we had separate roles for title/sub, we could use them; for now split on em dash if present
        t_text = title
        s_text = ""
        if " — " in title:
            parts = title.split(" — ", 1)
            t_text, s_text = parts[0], parts[1]
        font = painter.font()
        if self._text_only:
            font.setPointSize(max(10, font.pointSize()))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(title_rect, Qt.TextSingleLine | Qt.AlignVCenter, t_text)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor('#6b7280') if not (option.state & QStyle.State_Selected) else option.palette.highlightedText().color())
        painter.drawText(sub_rect, Qt.TextSingleLine | Qt.AlignVCenter, s_text)
        painter.restore()

    def sizeHint(self, option, index):  # noqa: D401
        return QSize(option.rect.width(), TEXT_ONLY_ROW_HEIGHT if self._text_only else ROW_HEIGHT)

class PlaylistEditWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Playlists")
        self.pm = PlaylistManager()
        self.selected_playlist1 = None
        self.selected_playlist2 = None
        self._last_dedupe_backup = None
        self._net = QNetworkAccessManager(self)
        # Global cache override (code-only toggle), default on
        self._cache_override = True
        self._thumb_loader = ThumbnailLoader(self._net, self, max_concurrency=12, cache_enabled=self._cache_override, cache_max_items=1500)
        # Explicit override (default ON)
        if self._cache_override:
            self._thumb_loader.set_cache_enabled(True)
        self._text_only = False
        # Debounce timers for viewport-aware lazy loading
        self._debounce1 = QTimer(self)
        self._debounce1.setSingleShot(True)
        self._debounce1.setInterval(80)
        self._debounce2 = QTimer(self)
        self._debounce2.setSingleShot(True)
        self._debounce2.setInterval(80)
        self._build_ui()
        # Apply persisted settings (text-only and cache max)
        try:
            settings = QSettings("MusicPlayer", "MusicPlayer")
            text_only = settings.value("playlist_edit/text_only", False, type=bool)
            cache_max = settings.value("playlist_edit/cache_max", 1500, type=int)
            self._toggle_text_only(text_only)
            self._on_cache_max_changed(cache_max)
        except Exception:
            pass
        # Set initial size (width=600, height=800) without restricting resizing
        try:
            self.resize(600, 800)
        except Exception:
            pass
        # Restore geometry if available; else center on open
        try:
            if not self._restore_window_state():
                self._center_on_parent()
        except Exception:
            pass
        # Keyboard shortcuts
        try:
            sc_remove = QShortcut(QKeySequence("Ctrl+D"), self)
            sc_remove.activated.connect(self._remove_duplicates)
            sc_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
            sc_undo.activated.connect(self._undo_remove)
            sc_save = QShortcut(QKeySequence("Ctrl+S"), self)
            sc_save.activated.connect(self._save_changes)
        except Exception:
            pass

    def showEvent(self, event):  # noqa: N802
        try:
            super().showEvent(event)
            # If no saved geometry, center on parent
            try:
                settings = QSettings("MusicPlayer", "MusicPlayer")
                if not settings.value("playlist_edit/geometry"):
                    self._center_on_parent()
            except Exception:
                pass
        except Exception:
            pass

    def closeEvent(self, event):  # noqa: N802
        try:
            self._save_window_state()
        except Exception:
            pass
        super().closeEvent(event)

    def _center_on_parent(self):
        try:
            parent = self.parentWidget()
            if parent is not None and parent.isVisible():
                pg = parent.frameGeometry()
                cg = self.frameGeometry()
                cg.moveCenter(pg.center())
                self.move(cg.topLeft())
            else:
                screen = QGuiApplication.primaryScreen()
                if screen:
                    sg = screen.availableGeometry()
                    cg = self.frameGeometry()
                    cg.moveCenter(sg.center())
                    self.move(cg.topLeft())
        except Exception:
            pass
    def _save_window_state(self) -> None:
        try:
            settings = QSettings("MusicPlayer", "MusicPlayer")
            settings.setValue("playlist_edit/geometry", self.saveGeometry())
        except Exception:
            pass

    def _restore_window_state(self) -> bool:
        try:
            settings = QSettings("MusicPlayer", "MusicPlayer")
            geo = settings.value("playlist_edit/geometry")
            if geo:
                self.restoreGeometry(geo)
                return True
        except Exception:
            pass
        return False

    def _build_ui(self):
        layout = QVBoxLayout(self)
        # Menubar with Settings
        menubar = QMenuBar(self)
        settings_menu = menubar.addMenu("Settings")
        act_opts = settings_menu.addAction("Playlist Editor...")
        act_opts.triggered.connect(self._open_inline_settings)
        layout.setMenuBar(menubar)
        # Playlist selectors
        selector_row = QHBoxLayout()
        self.combo1 = QComboBox()
        self.combo1.addItems(self.pm.names)
        self.combo1.currentTextChanged.connect(self._load_playlist1)
        self.lbl_pl1 = QLabel("Playlist 1:")
        selector_row.addWidget(self.lbl_pl1)
        selector_row.addWidget(self.combo1)
        self.combo2 = QComboBox()
        self.combo2.addItems(["<None>"] + self.pm.names)
        self.combo2.currentTextChanged.connect(self._load_playlist2)
        self.lbl_pl2 = QLabel("Playlist 2:")
        selector_row.addWidget(self.lbl_pl2)
        selector_row.addWidget(self.combo2)
        layout.addLayout(selector_row)
        # Mode toggle row for features (no inline cache controls)
        mode_row = QHBoxLayout()
        self.chk_merge = QCheckBox("Merge/Transfer Playlists")
        self.chk_merge.toggled.connect(self._toggle_merge_mode)
        mode_row.addWidget(self.chk_merge)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)
        # Splitter for dual playlist editing (each column has list + actions stacked vertically)
        self.splitter = QSplitter(Qt.Horizontal)
        # Column 1
        self.col1 = QWidget()
        self.col1_layout = QVBoxLayout(self.col1)
        self.col1_layout.setContentsMargins(0, 0, 0, 0)
        self.list1 = QListWidget()
        self.list1.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list1.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list1.customContextMenuRequested.connect(lambda pos: self._show_context_menu(self.list1, 1, pos))
        self.list1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list1.setIconSize(THUMB_SIZE)
        self.list1.setUniformItemSizes(True)
        self.col1_layout.addWidget(self.list1)
        # Copy 1->2 button (merge mode) — full width
        self.btn_copy_1to2 = QPushButton("Copy →")
        self.btn_copy_1to2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_copy_1to2.clicked.connect(self._copy_1to2)
        self.col1_layout.addWidget(self.btn_copy_1to2)
        # Remove duplicates row (button + badge in same row)
        self.btn_remove_dups = QPushButton("Remove Duplicates")
        self.btn_remove_dups.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_remove_dups.clicked.connect(self._remove_duplicates)
        self.lbl_dup_badge = QLabel("")
        self.lbl_dup_badge.setAlignment(Qt.AlignCenter)
        self.lbl_dup_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lbl_dup_badge.setStyleSheet("padding:4px 8px; border-radius:10px; background:#eee; color:#333;")
        self.row_remove_dups = QWidget()
        row = QHBoxLayout(self.row_remove_dups)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.btn_remove_dups)
        row.addWidget(self.lbl_dup_badge)
        row.addStretch(1)
        self.col1_layout.addWidget(self.row_remove_dups)
        # Undo remove — appears after a remove
        self.btn_undo_remove = QPushButton("Undo Remove")
        self.btn_undo_remove.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_undo_remove.setEnabled(False)
        self.btn_undo_remove.clicked.connect(self._undo_remove)
        self.col1_layout.addWidget(self.btn_undo_remove)
        self.splitter.addWidget(self.col1)
        # Column 2
        self.col2 = QWidget()
        self.col2_layout = QVBoxLayout(self.col2)
        self.col2_layout.setContentsMargins(0, 0, 0, 0)
        self.list2 = QListWidget()
        self.list2.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list2.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list2.customContextMenuRequested.connect(lambda pos: self._show_context_menu(self.list2, 2, pos))
        self.list2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list2.setIconSize(THUMB_SIZE)
        self.list2.setUniformItemSizes(True)
        self.col2_layout.addWidget(self.list2)
        # Copy 2->1 button — full width
        self.btn_copy_2to1 = QPushButton("← Copy")
        self.btn_copy_2to1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_copy_2to1.clicked.connect(self._copy_2to1)
        self.col2_layout.addWidget(self.btn_copy_2to1)
        self.splitter.addWidget(self.col2)
        layout.addWidget(self.splitter)
        # (Row removed: buttons now placed under their respective columns)
        # Save changes button
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        self.btn_save_changes = QPushButton("Save Changes")
        self.btn_save_changes.clicked.connect(self._save_changes)
        bottom_row.addWidget(self.btn_save_changes)
        layout.addLayout(bottom_row)
        # Use a custom delegate to paint card-like rows for thumbnails, dense when text-only
        try:
            d1 = PlaylistItemDelegate(self._thumb_loader, self.list1)
            d1.set_text_only(self._text_only)
            self.list1.setItemDelegate(d1)
            d2 = PlaylistItemDelegate(self._thumb_loader, self.list2)
            d2.set_text_only(self._text_only)
            self.list2.setItemDelegate(d2)
        except Exception:
            pass
        # Connect debounce timers once
        try:
            self._debounce1.timeout.connect(lambda: self._load_visible_thumbs(self.list1))
            self._debounce2.timeout.connect(lambda: self._load_visible_thumbs(self.list2))
        except Exception:
            pass
        # Lazy loading: trigger on scroll with named slots (easier to disconnect)
        try:
            self.list1.verticalScrollBar().valueChanged.connect(self._on_scroll1)
            self.list2.verticalScrollBar().valueChanged.connect(self._on_scroll2)
            self._scroll_connected1 = True
            self._scroll_connected2 = True
        except Exception:
            self._scroll_connected1 = False
            self._scroll_connected2 = False
        self._load_playlist1(self.combo1.currentText())
        self._load_playlist2(self.combo2.currentText())
        # Initialize in single-playlist mode
        self._toggle_merge_mode(False)
        # Initialize duplicate badge
        try:
            self._update_dup_badge()
        except Exception:
            pass

    def _toggle_merge_mode(self, enabled: bool):
        try:
            # Toggle visibility of Playlist 2 UI and copy controls
            self.lbl_pl2.setVisible(bool(enabled))
            self.combo2.setVisible(bool(enabled))
            self.col2.setVisible(bool(enabled))
            self.btn_copy_1to2.setVisible(bool(enabled))
            self.btn_copy_2to1.setVisible(bool(enabled))
            # Toggle remove/undo duplicates row (shown only in single mode)
            self.row_remove_dups.setVisible(not bool(enabled))
            self.btn_undo_remove.setVisible(not bool(enabled))
            # Hide splitter handle when single mode
            self.splitter.setHandleWidth(5 if enabled else 0)
        except Exception:
            pass

    def _remove_duplicates(self):
        try:
            name = self.combo1.currentText()
            if not name:
                return
            p = self.pm.get(name)
            if not p or not getattr(p, 'media_files', None):
                return
            # Confirm removal
            res = QMessageBox.question(self, "Remove Duplicates", "This will remove duplicate songs from the playlist. Continue?", QMessageBox.Yes | QMessageBox.No)
            if res != QMessageBox.Yes:
                return
            # Backup for undo
            self._last_dedupe_backup = list(p.media_files)
            seen = set()
            unique = []
            for it in p.media_files:
                key = self._item_key(it)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(it)
            removed = max(0, len(p.media_files) - len(unique))
            if removed == 0:
                QMessageBox.information(self, "Duplicates", "No duplicate songs found.")
                return
            p.media_files = unique
            try:
                self.pm._persist()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._load_playlist1(name)
            # Enable undo
            try:
                self.btn_undo_remove.setEnabled(True)
            except Exception:
                pass
            QMessageBox.information(self, "Duplicates", f"Removed {removed} duplicate song(s).")
            try:
                self._update_dup_badge()
            except Exception:
                pass
        except Exception:
            QMessageBox.warning(self, "Duplicates", "Failed to remove duplicates.")

    def _undo_remove(self):
        try:
            if not self._last_dedupe_backup:
                return
            name = self.combo1.currentText()
            if not name:
                return
            p = self.pm.get(name)
            if not p:
                return
            p.media_files = self._last_dedupe_backup
            try:
                self.pm._persist()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._load_playlist1(name)
            self._last_dedupe_backup = None
            try:
                self.btn_undo_remove.setEnabled(False)
            except Exception:
                pass
            QMessageBox.information(self, "Undo", "Restored playlist to its previous state.")
            try:
                self._update_dup_badge()
            except Exception:
                pass
        except Exception:
            QMessageBox.warning(self, "Undo", "Failed to undo the last change.")

    def _update_dup_badge(self):
        name = self.combo1.currentText()
        count = self._duplicate_count(name)
        self.lbl_dup_badge.setText(f"Duplicates: {count}")
        if count > 0:
            self.lbl_dup_badge.setStyleSheet("padding:4px 8px; border-radius:10px; background:#fee2e2; color:#b91c1c;")
            self.btn_remove_dups.setEnabled(True)
        else:
            self.lbl_dup_badge.setStyleSheet("padding:4px 8px; border-radius:10px; background:#eef2ff; color:#1e3a8a;")
            self.btn_remove_dups.setEnabled(False)

    def _duplicate_count(self, name):
        try:
            p = self.pm.get(name)
            if not p:
                return 0
            seen = set()
            dups = 0
            for it in p.media_files:
                key = self._item_key(it)
                if key in seen:
                    dups += 1
                else:
                    seen.add(key)
            return dups
        except Exception:
            return 0

    def _save_changes(self):
        try:
            # Save current order for playlist 1
            name1 = self.combo1.currentText()
            if name1:
                p1 = self.pm.get(name1)
                if p1:
                    keys1 = [self.list1.item(i).data(Qt.UserRole) for i in range(self.list1.count())]
                    keymap1 = {self._item_key(it): it for it in p1.media_files}
                    new_items1 = [keymap1[k] for k in keys1 if k in keymap1]
                    p1.media_files = new_items1
            # Save current order for playlist 2 (if merge mode and playlist chosen)
            if self.chk_merge.isChecked():
                name2 = self.combo2.currentText()
                if name2 and name2 != "<None>":
                    p2 = self.pm.get(name2)
                    if p2:
                        keys2 = [self.list2.item(i).data(Qt.UserRole) for i in range(self.list2.count())]
                        keymap2 = {self._item_key(it): it for it in p2.media_files}
                        new_items2 = [keymap2[k] for k in keys2 if k in keymap2]
                        p2.media_files = new_items2
            # Persist once
            try:
                self.pm._persist()  # type: ignore[attr-defined]
            except Exception:
                pass
            # Reload views to reflect saved order
            if name1:
                self._load_playlist1(name1)
            if self.chk_merge.isChecked():
                name2 = self.combo2.currentText()
                if name2 and name2 != "<None>":
                    self._load_playlist2(name2)
            QMessageBox.information(self, "Saved", "Changes saved.")
        except Exception:
            QMessageBox.warning(self, "Save", "Failed to save changes.")

    def _load_playlist1(self, name):
        self.selected_playlist1 = name
        self.list1.clear()
        p = self.pm.get(name)
        if p:
            MAX_WIDGET_ITEMS = 400
            use_widgets = (len(p.media_files) <= MAX_WIDGET_ITEMS) and (not getattr(self, "_text_only", False))
            for it in p.media_files:
                itemw = QListWidgetItem(self.list1)
                itemw.setData(Qt.UserRole, self._item_key(it))
                if getattr(it, "thumbnail_url", None):
                    itemw.setData(THUMB_URL_ROLE, it.thumbnail_url)
                if use_widgets:
                    w = QWidget()
                    lay = QHBoxLayout(w)
                    lay.setContentsMargins(4, 4, 4, 4)
                    thumb = QLabel()
                    thumb.setFixedSize(THUMB_SIZE)
                    lay.addWidget(thumb)
                    box = QVBoxLayout()
                    box.setContentsMargins(0, 0, 0, 0)
                    t = QLabel(it.title)
                    t.setStyleSheet("font-weight:600;color:#111")
                    sub = QLabel(getattr(it, "artist", getattr(it, "uploader", "")))
                    sub.setStyleSheet("color:#555")
                    box.addWidget(t)
                    box.addWidget(sub)
                    lay.addLayout(box)
                    w.setFixedHeight(ROW_HEIGHT)
                    itemw.setSizeHint(QSize(itemw.sizeHint().width(), ROW_HEIGHT))
                    self.list1.addItem(itemw)
                    self.list1.setItemWidget(itemw, w)
                else:
                    title = it.title
                    sub = getattr(it, "artist", getattr(it, "uploader", ""))
                    itemw.setText(f"{title} — {sub}" if sub else title)
                    new_h = TEXT_ONLY_ROW_HEIGHT if getattr(self, "_text_only", False) else ROW_HEIGHT
                    itemw.setSizeHint(QSize(itemw.sizeHint().width(), new_h))
                    self.list1.addItem(itemw)
            try:
                self._load_visible_thumbs(self.list1)
            except Exception:
                pass

    def _item_key(self, it):
        prov = getattr(it, "provider", None)
        prov_val = prov.value if hasattr(prov, "value") else str(prov)
        if prov_val == "local":
            return f"{prov_val}:{getattr(it, 'file_path', '')}"
        sid = getattr(it, "source_id", None)
        url = getattr(it, "url", None)
        return f"{prov_val}:{sid or url or ''}"

    # Removed legacy _load_thumb; lazy loader handles thumbnails

    def _load_visible_thumbs(self, list_widget):
        try:
            # In text-only mode, avoid any image loading
            if getattr(self, "_text_only", False):
                return
            viewport = list_widget.viewport()
            vrect = viewport.rect()
            count = list_widget.count()
            for i in range(count):
                item = list_widget.item(i)
                if item.data(THUMB_LOADED_ROLE):
                    continue
                url = item.data(THUMB_URL_ROLE)
                if not url:
                    continue
                rect = list_widget.visualItemRect(item)
                if not rect.isValid():
                    continue
                if rect.bottom() < vrect.top() or rect.top() > vrect.bottom():
                    continue
                w = list_widget.itemWidget(item)
                if w is not None:
                    labels = w.findChildren(QLabel)
                    if labels:
                        lbl = labels[0]
                        self._thumb_loader.request_label(url, item, lbl, size=(THUMB_SIZE.width(), THUMB_SIZE.height()))
                else:
                    # Prefetch into cache; delegate paints the pixmap
                    self._thumb_loader.request_cache(url, item)
        except Exception:
            pass

    def _on_scroll_debounced(self, which):
        try:
            # If text-only, do nothing; no thumbnails to load
            if getattr(self, "_text_only", False):
                return
            if which == 1:
                if self._debounce1.isActive():
                    self._debounce1.stop()
                self._debounce1.start()
            else:
                if self._debounce2.isActive():
                    self._debounce2.stop()
                self._debounce2.start()
        except Exception:
            pass

    def _toggle_text_only(self, enabled: bool):
        try:
            self._text_only = bool(enabled)
            try:
                settings = QSettings("MusicPlayer", "MusicPlayer")
                settings.setValue("playlist_edit/text_only", self._text_only)
            except Exception:
                pass
            # Connect/disconnect scroll handlers and stop timers as needed
            try:
                if self._text_only:
                    if getattr(self, "_scroll_connected1", False):
                        try:
                            self.list1.verticalScrollBar().valueChanged.disconnect(self._on_scroll1)
                        except Exception:
                            pass
                        self._scroll_connected1 = False
                    if getattr(self, "_scroll_connected2", False):
                        try:
                            self.list2.verticalScrollBar().valueChanged.disconnect(self._on_scroll2)
                        except Exception:
                            pass
                        self._scroll_connected2 = False
                    try:
                        self._debounce1.stop()
                        self._debounce2.stop()
                    except Exception:
                        pass
                else:
                    if not getattr(self, "_scroll_connected1", False):
                        try:
                            self.list1.verticalScrollBar().valueChanged.connect(self._on_scroll1)
                            self._scroll_connected1 = True
                        except Exception:
                            pass
                    if not getattr(self, "_scroll_connected2", False):
                        try:
                            self.list2.verticalScrollBar().valueChanged.connect(self._on_scroll2)
                            self._scroll_connected2 = True
                        except Exception:
                            pass
            except Exception:
                pass
            # Update delegates to respect this mode
            d1 = self.list1.itemDelegate()
            if isinstance(d1, PlaylistItemDelegate):
                d1.set_text_only(self._text_only)
            d2 = self.list2.itemDelegate()
            if isinstance(d2, PlaylistItemDelegate):
                d2.set_text_only(self._text_only)
            # Adjust row heights for density
            new_h = TEXT_ONLY_ROW_HEIGHT if self._text_only else ROW_HEIGHT
            try:
                for lw in (self.list1, self.list2):
                    for i in range(lw.count()):
                        it = lw.item(i)
                        it.setSizeHint(QSize(it.sizeHint().width(), new_h))
                    try:
                        lw.doItemsLayout()
                    except Exception:
                        pass
            except Exception:
                pass
            # Force repaint and avoid new loads when enabled
            self.list1.viewport().update()
            self.list2.viewport().update()
            if not self._text_only:
                # When turning thumbnails back on, load visible ones
                self._load_visible_thumbs(self.list1)
                self._load_visible_thumbs(self.list2)
        except Exception:
            pass

    def _on_cache_max_changed(self, n: int):
        try:
            self._thumb_loader.set_cache_max_items(int(n))
            try:
                settings = QSettings("MusicPlayer", "MusicPlayer")
                settings.setValue("playlist_edit/cache_max", int(n))
            except Exception:
                pass
        except Exception:
            pass

    def _on_scroll1(self, _val: int):
        self._on_scroll_debounced(1)

    def _on_scroll2(self, _val: int):
        self._on_scroll_debounced(2)

    def _open_inline_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Playlist Editor Settings")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        settings = QSettings("MusicPlayer", "MusicPlayer")
        text_only = settings.value("playlist_edit/text_only", False, type=bool)
        cache_max = settings.value("playlist_edit/cache_max", 1500, type=int)
        cb_text = QCheckBox("Text-only (no thumbnails)")
        cb_text.setChecked(text_only)
        sp_cache = QSpinBox()
        sp_cache.setRange(100, 10000)
        sp_cache.setSingleStep(100)
        sp_cache.setValue(cache_max)
        form.addRow("Text-only mode", cb_text)
        form.addRow("Thumbnail cache max", sp_cache)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        lay.addWidget(buttons)

        def on_save():
            # Apply via existing handlers (which also persist)
            self._toggle_text_only(cb_text.isChecked())
            self._on_cache_max_changed(sp_cache.value())
            dlg.accept()

        buttons.accepted.connect(on_save)
        buttons.rejected.connect(dlg.reject)
        try:
            dlg.setModal(False)
            dlg.setWindowModality(Qt.NonModal)
            dlg.show()
        except Exception:
            try:
                dlg.exec()
            except Exception:
                pass

    def _load_playlist2(self, name):
        if name == "<None>":
            self.selected_playlist2 = None
            self.list2.clear()
            return
        self.selected_playlist2 = name
        self.list2.clear()
        p = self.pm.get(name)
        if p:
            MAX_WIDGET_ITEMS = 400
            use_widgets = (len(p.media_files) <= MAX_WIDGET_ITEMS) and (not getattr(self, "_text_only", False))
            for it in p.media_files:
                itemw = QListWidgetItem(self.list2)
                itemw.setData(Qt.UserRole, self._item_key(it))
                if getattr(it, "thumbnail_url", None):
                    itemw.setData(THUMB_URL_ROLE, it.thumbnail_url)
                if use_widgets:
                    w = QWidget()
                    lay = QHBoxLayout(w)
                    lay.setContentsMargins(4, 4, 4, 4)
                    thumb = QLabel()
                    thumb.setFixedSize(THUMB_SIZE)
                    # deferred loading
                    lay.addWidget(thumb)
                    box = QVBoxLayout()
                    box.setContentsMargins(0, 0, 0, 0)
                    t = QLabel(it.title)
                    t.setStyleSheet("font-weight:600;color:#111")
                    sub = QLabel(getattr(it, "artist", getattr(it, "uploader", "")))
                    sub.setStyleSheet("color:#555")
                    box.addWidget(t)
                    box.addWidget(sub)
                    lay.addLayout(box)
                    w.setFixedHeight(ROW_HEIGHT)
                    itemw.setSizeHint(QSize(itemw.sizeHint().width(), ROW_HEIGHT))
                    self.list2.addItem(itemw)
                    self.list2.setItemWidget(itemw, w)
                else:
                    title = it.title
                    sub = getattr(it, "artist", getattr(it, "uploader", ""))
                    itemw.setText(f"{title} — {sub}" if sub else title)
                    new_h = TEXT_ONLY_ROW_HEIGHT if getattr(self, "_text_only", False) else ROW_HEIGHT
                    itemw.setSizeHint(QSize(itemw.sizeHint().width(), new_h))
                    self.list2.addItem(itemw)
            try:
                self._load_visible_thumbs(self.list2)
            except Exception:
                pass

    def _show_context_menu(self, list_widget, which, pos):
        menu = QMenu(list_widget)
        act_remove = menu.addAction("Remove Selected")
        act_move_up = menu.addAction("Move Up")
        act_move_down = menu.addAction("Move Down")
        chosen = menu.exec_(list_widget.mapToGlobal(pos))
        selected = list_widget.selectedItems()
        if not selected:
            return
        rows = sorted([list_widget.row(item) for item in selected])
        if chosen == act_remove:
            for row in reversed(rows):
                list_widget.takeItem(row)
                self._remove_from_playlist(which, row)
        elif chosen == act_move_up:
            for row in rows:
                if row > 0:
                    item = list_widget.takeItem(row)
                    list_widget.insertItem(row - 1, item)
        elif chosen == act_move_down:
            for row in reversed(rows):
                if row < list_widget.count() - 1:
                    item = list_widget.takeItem(row)
                    list_widget.insertItem(row + 1, item)

    def _remove_from_playlist(self, which, row):
        if which == 1 and self.selected_playlist1:
            self.pm.remove(self.selected_playlist1, row)
        elif which == 2 and self.selected_playlist2:
            self.pm.remove(self.selected_playlist2, row)

    def _copy_1to2(self):
        if not self.selected_playlist1 or not self.selected_playlist2:
            return
        selected = self.list1.selectedItems()
        if not selected:
            return
        p1 = self.pm.get(self.selected_playlist1)
        p2 = self.pm.get(self.selected_playlist2)
        # Build set of keys for playlist 2
        keys2 = set(self._item_key(it) for it in p2.media_files)
        for item in selected:
            idx = self.list1.row(item)
            mf = p1.media_files[idx]
            key = self._item_key(mf)
            if key in keys2:
                continue  # Skip duplicates
            self.pm.add(self.selected_playlist2, mf)
            self._load_playlist2(self.selected_playlist2)

    def _copy_2to1(self):
        if not self.selected_playlist1 or not self.selected_playlist2:
            return
        selected = self.list2.selectedItems()
        if not selected:
            return
        p2 = self.pm.get(self.selected_playlist2)
        p1 = self.pm.get(self.selected_playlist1)
        # Build set of keys for playlist 1
        keys1 = set(self._item_key(it) for it in p1.media_files)
        for item in selected:
            idx = self.list2.row(item)
            mf = p2.media_files[idx]
            key = self._item_key(mf)
            if key in keys1:
                continue  # Skip duplicates
            self.pm.add(self.selected_playlist1, mf)
            self._load_playlist1(self.selected_playlist1)
