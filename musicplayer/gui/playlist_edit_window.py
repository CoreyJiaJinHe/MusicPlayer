from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QLabel, QComboBox, QSplitter, QAbstractItemView, QMenu, QMessageBox, QWidget, QListWidgetItem
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtCore import QUrl
from PySide6.QtCore import Qt
from MusicPlayer.playlist.manager import PlaylistManager

class PlaylistEditWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Playlists")
        self.pm = PlaylistManager()
        self.selected_playlist1 = None
        self.selected_playlist2 = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        # Playlist selectors
        selector_row = QHBoxLayout()
        self.combo1 = QComboBox()
        self.combo1.addItems(self.pm.names)
        self.combo1.currentTextChanged.connect(self._load_playlist1)
        selector_row.addWidget(QLabel("Playlist 1:"))
        selector_row.addWidget(self.combo1)
        self.combo2 = QComboBox()
        self.combo2.addItems(["<None>"] + self.pm.names)
        self.combo2.currentTextChanged.connect(self._load_playlist2)
        selector_row.addWidget(QLabel("Playlist 2:"))
        selector_row.addWidget(self.combo2)
        layout.addLayout(selector_row)
        # Splitter for dual playlist editing
        self.splitter = QSplitter(Qt.Horizontal)
        # Playlist 1
        self.list1 = QListWidget()
        self.list1.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list1.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list1.customContextMenuRequested.connect(lambda pos: self._show_context_menu(self.list1, 1, pos))
        self.splitter.addWidget(self.list1)
        # Playlist 2
        self.list2 = QListWidget()
        self.list2.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list2.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list2.customContextMenuRequested.connect(lambda pos: self._show_context_menu(self.list2, 2, pos))
        self.splitter.addWidget(self.list2)
        layout.addWidget(self.splitter)
        # Copy button
        copy_row = QHBoxLayout()
        self.btn_copy_1to2 = QPushButton("Copy →")
        self.btn_copy_1to2.clicked.connect(self._copy_1to2)
        copy_row.addWidget(self.btn_copy_1to2)
        self.btn_copy_2to1 = QPushButton("← Copy")
        self.btn_copy_2to1.clicked.connect(self._copy_2to1)
        copy_row.addWidget(self.btn_copy_2to1)
        layout.addLayout(copy_row)
        self._load_playlist1(self.combo1.currentText())
        self._load_playlist2(self.combo2.currentText())

    def _load_playlist1(self, name):
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import QUrl
        from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
        self.selected_playlist1 = name
        self.list1.clear()
        p = self.pm.get(name)
        if p:
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
                itemw = QListWidgetItem(self.list1)
                itemw.setSizeHint(w.sizeHint())
                itemw.setData(Qt.UserRole, self._item_key(it))
                self.list1.addItem(itemw)
                self.list1.setItemWidget(itemw, w)

    def _item_key(self, it):
        prov = getattr(it, "provider", None)
        prov_val = prov.value if hasattr(prov, "value") else str(prov)
        if prov_val == "local":
            return f"{prov_val}:{getattr(it, 'file_path', '')}"
        sid = getattr(it, "source_id", None)
        url = getattr(it, "url", None)
        return f"{prov_val}:{sid or url or ''}"

    def _load_thumb(self, url, label):
        try:
            from PySide6.QtNetwork import QNetworkRequest
            req = QNetworkRequest(QUrl(url))
            net = QNetworkAccessManager(self)
            reply = net.get(req)
            def _on_finished():
                from PySide6.QtGui import QPixmap
                try:
                    data = reply.readAll()
                    pm = QPixmap()
                    if pm.loadFromData(bytes(data)):
                        label.setPixmap(pm.scaled(80, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                except Exception:
                    pass
                finally:
                    reply.deleteLater()
            reply.finished.connect(_on_finished)
        except Exception:
            pass

    def _load_playlist2(self, name):
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import QUrl
        from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
        if name == "<None>":
            self.selected_playlist2 = None
            self.list2.clear()
            return
        self.selected_playlist2 = name
        self.list2.clear()
        p = self.pm.get(name)
        if p:
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
                itemw = QListWidgetItem(self.list2)
                itemw.setSizeHint(w.sizeHint())
                itemw.setData(Qt.UserRole, self._item_key(it))
                self.list2.addItem(itemw)
                self.list2.setItemWidget(itemw, w)

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
