from typing import Optional
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QMenuBar,
    QDialog,
    QVBoxLayout,
    QCheckBox,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QWidget,
    QSpinBox,
    QFormLayout,
)

from MusicPlayer.config.loader import (
    save_config,
)


class MenuController:
    """Builds the menubar and owns related settings dialogs."""

    def __init__(self, main_window) -> None:
        self.main = main_window

    def attach(self) -> None:
        menubar = QMenuBar(self.main)
        settings_menu = menubar.addMenu("Settings")

        act_music = settings_menu.addAction("Music Folder...")
        act_music.triggered.connect(self.main._choose_music_folder)

        act_flags = settings_menu.addAction("WebEngine Flags...")
        act_flags.triggered.connect(self._open_flags_dialog)

        act_env = settings_menu.addAction("Edit API Keys (.env)...")
        act_env.triggered.connect(self._open_env_dialog)

        act_adv_details = settings_menu.addAction("Advanced Details...")
        act_adv_details.triggered.connect(self._open_advanced_details_dialog)

        # Playlist Editor settings are now part of the editor window UI

        adv_menu = menubar.addMenu("Advanced")
        act_play_combined = adv_menu.addAction("Play Combined...")
        act_play_combined_shuffle = adv_menu.addAction("Play Combined (Shuffle)")
        act_show_unavailable = adv_menu.addAction("Show Unavailable...")
        act_show_deleted = adv_menu.addAction("Show Deleted...")
        act_play_combined.triggered.connect(lambda: self.main._open_play_combined_dialog(False))
        act_play_combined_shuffle.triggered.connect(lambda: self.main._open_play_combined_dialog(True))
        act_show_unavailable.triggered.connect(self._open_unavailable_dialog)
        act_show_deleted.triggered.connect(self._open_deleted_dialog)

        self.main.setMenuBar(menubar)

    def _open_advanced_details_dialog(self) -> None:
        dlg = QDialog(self.main)
        dlg.setWindowTitle("Advanced Details Settings")
        layout = QVBoxLayout(dlg)
        cb_adv = QCheckBox("Show Advanced Details for Playlist Items")
        cb_adv.setChecked(self.main.advanced_details)
        layout.addWidget(cb_adv)
        cb_dedupe = QCheckBox("Deduplicate merged playlists")
        cb_dedupe.setChecked(getattr(self.main, 'dedupe_merged', True))
        layout.addWidget(cb_dedupe)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_ok():
            self.main.advanced_details = cb_adv.isChecked()
            self.main.dedupe_merged = cb_dedupe.isChecked()
            self.main._on_playlist_selected(self.main._current_playlist_name() or "")
            dlg.accept()

        buttons.accepted.connect(on_ok)
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

    # Removed: _open_playlist_editor_settings; settings live in the editor window

    def _open_flags_dialog(self) -> None:
        dlg = QDialog(self.main)
        dlg.setWindowTitle("WebEngine Flags")
        layout = QVBoxLayout(dlg)

        current = (self.main.cfg.webengine_flags or "").split()
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
            self.main.cfg.webengine_flags = " ".join(flags) if flags else None
            save_config(self.main.cfg)
            QMessageBox.information(
                self.main,
                "Saved",
                "Flags saved. Please restart the application for changes to take effect.",
            )
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

    def _open_unavailable_dialog(self) -> None:
        """Show a dialog listing all unavailable items across playlists as cards."""
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QHBoxLayout, QVBoxLayout
        dlg = QDialog(self.main)
        dlg.setWindowTitle("Unavailable Items")
        try:
            dlg.resize(500, 500)
        except Exception:
            pass
        lay = QVBoxLayout(dlg)
        info = QLabel("Items marked as unavailable. Click Close to dismiss.")
        info.setStyleSheet("color:#666")
        lay.addWidget(info)
        lw = QListWidget()
        lay.addWidget(lw)
        # Collect unavailable items and which playlists contain them
        items_map = []  # list of tuples (item, [playlist_names])
        try:
            for name in self.main.pm.names:
                p = self.main.pm.get(name)
                if not p:
                    continue
                for it in p.media_files:
                    if getattr(it, "unavailable", False):
                        key = self.main._item_key(it)
                        found = None
                        for j, (existing, pls) in enumerate(items_map):
                            if self.main._item_key(existing) == key:
                                found = j
                                break
                        if found is None:
                            items_map.append((it, [name]))
                        else:
                            items_map[found][1].append(name)
        except Exception:
            pass

        for it, pls in items_map:
            w = QWidget()
            hbox = QHBoxLayout(w)
            thumb = QLabel()
            thumb.setFixedSize(120, 72)
            thumb.setAlignment(Qt.AlignCenter)
            if getattr(it, 'thumbnail_url', None):
                try:
                    self.main._load_thumb(it.thumbnail_url, thumb)
                except Exception:
                    pass
            hbox.addWidget(thumb)
            vbox = QVBoxLayout()
            title = QLabel(it.title)
            title.setStyleSheet("font-weight:600;color:#111")
            artist = QLabel(getattr(it, 'artist', getattr(it, 'uploader', '')))
            artist.setStyleSheet("color:#555")
            dur_val = getattr(it, 'duration', 0) or 0
            def fmt_dur(sec:int) -> str:
                m, s = divmod(int(sec), 60)
                return f"{m}:{s:02d}"
            duration = QLabel(f"Duration: {fmt_dur(dur_val)}")
            duration.setStyleSheet("color:#555")
            playlists_lbl = QLabel(f"Playlists: {', '.join(sorted(set(pls)))}")
            playlists_lbl.setStyleSheet("color:#333")
            vbox.addWidget(title)
            vbox.addWidget(artist)
            vbox.addWidget(duration)
            vbox.addWidget(playlists_lbl)
            hbox.addLayout(vbox)
            itemw = QListWidgetItem(lw)
            itemw.setSizeHint(w.sizeHint())
            lw.addItem(itemw)
            lw.setItemWidget(itemw, w)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        btn_mark_all = buttons.addButton("DEBUG: Mark All Available", QDialogButtonBox.ActionRole)
        lay.addWidget(buttons)

        def _mark_all_available() -> None:
            try:
                keys = set()
                for it, _pls in items_map:
                    try:
                        keys.add(self.main._item_key(it))
                    except Exception:
                        pass
                for name in self.main.pm.names:
                    p = self.main.pm.get(name)
                    if not p:
                        continue
                    for mf in getattr(p, 'media_files', []):
                        try:
                            if getattr(mf, 'unavailable', False) and self.main._item_key(mf) in keys:
                                mf.unavailable = False
                        except Exception:
                            pass
                try:
                    self.main.pm._persist()  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    self.main._refresh_queue_cards()
                except Exception:
                    pass
            finally:
                dlg.accept()

        btn_mark_all.clicked.connect(_mark_all_available)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        try:
            dlg.setModal(False)
            dlg.setWindowModality(Qt.NonModal)
            dlg.show()
        except Exception:
            try:
                dlg.exec()
            except Exception:
                pass

    def _open_deleted_dialog(self) -> None:
        """Show a dialog listing deleted items across playlists."""
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QHBoxLayout, QVBoxLayout

        dlg = QDialog(self.main)
        dlg.setWindowTitle("Deleted Items")
        try:
            dlg.resize(500, 500)
        except Exception:
            pass
        lay = QVBoxLayout(dlg)
        info = QLabel("Items whose title indicates they were deleted.")
        info.setStyleSheet("color:#666")
        lay.addWidget(info)
        lw = QListWidget()
        lay.addWidget(lw)

        items_map = []  # list of tuples (item, [playlist_names])
        try:
            for name in self.main.pm.names:
                p = self.main.pm.get(name)
                if not p:
                    continue
                for it in p.media_files:
                    title = (getattr(it, "title", "") or "").strip().lower()
                    if title != "deleted video":
                        continue
                    key = self.main._item_key(it)
                    found = None
                    for j, (existing, pls) in enumerate(items_map):
                        if self.main._item_key(existing) == key:
                            found = j
                            break
                    if found is None:
                        items_map.append((it, [name]))
                    else:
                        items_map[found][1].append(name)
        except Exception:
            pass

        for it, pls in items_map:
            w = QWidget()
            hbox = QHBoxLayout(w)
            vbox = QVBoxLayout()
            title_text = getattr(it, "source_id", None) or "(missing source id)"
            title = QLabel(str(title_text))
            title.setStyleSheet("font-weight:600;color:#111")
            provider_val = getattr(it, "provider", "")
            provider_str = provider_val.value if hasattr(provider_val, "value") else str(provider_val)
            provider = QLabel(f"Provider: {provider_str}")
            provider.setStyleSheet("color:#555")
            playlists_lbl = QLabel(f"Playlists: {', '.join(sorted(set(pls)))}")
            playlists_lbl.setStyleSheet("color:#333")
            vbox.addWidget(title)
            vbox.addWidget(provider)
            vbox.addWidget(playlists_lbl)
            hbox.addLayout(vbox)
            itemw = QListWidgetItem(lw)
            itemw.setSizeHint(w.sizeHint())
            lw.addItem(itemw)
            lw.setItemWidget(itemw, w)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        lay.addWidget(buttons)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        try:
            dlg.setModal(False)
            dlg.setWindowModality(Qt.NonModal)
            dlg.show()
        except Exception:
            try:
                dlg.exec()
            except Exception:
                pass

    def _open_env_dialog(self) -> None:
        from MusicPlayer.config.loader import (
            get_youtube_api_key,
            get_soundcloud_client_id,
            set_youtube_api_key,
            set_soundcloud_client_id,
        )
        from PySide6.QtWidgets import QFormLayout, QLineEdit

        dlg = QDialog(self.main)
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
                self.main,
                "Saved",
                ".env updated. Restart the application to load new keys.",
            )
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
