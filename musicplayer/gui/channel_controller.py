from typing import Optional, Any, List
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QListWidgetItem, QMessageBox, QHBoxLayout, QLabel, QVBoxLayout

# Local imports used for YouTube channel operations
from MusicPlayer.config.loader import get_youtube_api_key
from MusicPlayer.search.youtube import (
    search_youtube_channels,
    resolve_channel_id,
    list_channel_videos,
)


class ChannelVideosController:
    """Encapsulates YouTube channel browsing, paging, and save-all logic.

    This controller coordinates with the MainWindow's UI widgets (results list,
    action buttons) and delegates rendering via helpers on the MainWindow.
    """

    def __init__(self, main_window: QWidget) -> None:
        # MainWindow reference for accessing UI and helper methods
        self.main = main_window
        # Paging/context state for channel videos
        self._channel_ctx = {
            "channel_id": None,
            "channel_name": None,
            "prev_tokens": [],
            "current_token": None,
            "next_token": None,
            "cache": {},
        }

    # --- Context helpers ---
    def reset_for_new_search(self) -> None:
        """Clear context when a new search (any source) is performed."""
        try:
            self._channel_ctx["cache"] = {}
            self._channel_ctx["channel_id"] = None
            self._channel_ctx["channel_name"] = None
            self._channel_ctx["prev_tokens"] = []
            self._channel_ctx["current_token"] = None
            self._channel_ctx["next_token"] = None
        except Exception:
            pass

    # --- Results handling for Channels ---
    def populate_channel_results(self, channels: List[Any]) -> None:
        """Render channel search results with profile image and title."""
        try:
            self.main.results.clear()
            logging.warning("Populate channel results: %d entries", len(channels or []))
            for ch in channels or []:
                w = QWidget()
                lay = QHBoxLayout(w)
                thumb = QLabel()
                thumb.setFixedSize(60, 60)
                thumb.setAlignment(Qt.AlignCenter)
                turl = getattr(ch, 'thumbnail_url', None)
                if turl:
                    try:
                        self.main._load_thumb(turl, thumb)
                    except Exception:
                        pass
                lay.addWidget(thumb)
                box = QVBoxLayout()
                title = QLabel(getattr(ch, 'channel_name', ''))
                title.setStyleSheet("font-weight:600;color:#111")
                url_lbl = QLabel(getattr(ch, 'source_url', ''))
                url_lbl.setStyleSheet("color:#555")
                box.addWidget(title)
                box.addWidget(url_lbl)
                lay.addLayout(box)
                itemw = QListWidgetItem(self.main.results)
                itemw.setSizeHint(w.sizeHint())
                # Store an identifier for this being a channel entry
                itemw.setData(Qt.UserRole, {"type": "channel", "id": getattr(ch, 'channel_id', None)})
                self.main.results.addItem(itemw)
                self.main.results.setItemWidget(itemw, w)
            # Disable Add-to-Playlist while showing channels, and hide channel-videos controls
            try:
                self.main.btn_add.setEnabled(False)
                self.main.btn_back_channels.setVisible(False)
                self.main.btn_prev_page.setVisible(False)
                self.main.btn_next_page.setVisible(False)
                self.main.btn_save_all.setVisible(False)
            except Exception:
                pass
        except Exception:
            pass

    def on_results_double_clicked(self, item) -> None:  # noqa: ANN001
        """Handle activation on a channel entry to fetch its videos."""
        try:
            if self.main.source.currentText() != "YouTube":
                return
            mode = self.main.youtube_mode.currentText() if self.main.youtube_mode.isVisible() else "Videos"
            if mode != "Channels":
                return
            api_key = get_youtube_api_key()
            if not api_key:
                return
            # Determine which channel was clicked
            row = self.main.results.row(item)
            channels = getattr(self.main, "_found_channels", [])
            if row < 0 or row >= len(channels):
                return
            ch = channels[row]
            logging.warning("Channel selected row=%d id=%s name=%s", row, getattr(ch, 'channel_id', None), getattr(ch, 'channel_name', None))
            cid = getattr(ch, 'channel_id', None)
            if not cid:
                return
            # Enter channel videos view with paging
            self.enter_channel_videos(cid, getattr(ch, 'channel_name', '') or getattr(ch, 'source_url', ''))
        except Exception:
            pass

    def enter_channel_videos(self, channel_id: str, channel_name: str) -> None:
        """Switch UI into channel videos view, init paging and fetch first page."""
        try:
            logging.warning("Enter channel videos: id=%s name=%s", channel_id, channel_name)
            self._channel_ctx["channel_id"] = channel_id
            self._channel_ctx["channel_name"] = channel_name
            self._channel_ctx["prev_tokens"] = []
            self._channel_ctx["current_token"] = None
            self._channel_ctx["next_token"] = None
            # New channel selection wipes cached pages
            try:
                self._channel_ctx["cache"] = {}
            except Exception:
                pass
            # Show channel controls and allow adding videos
            self.main.btn_back_channels.setVisible(True)
            self.main.btn_prev_page.setVisible(False)
            self.main.btn_next_page.setVisible(False)
            self.main.btn_save_all.setVisible(True)
            self.main.btn_add.setEnabled(True)
            # Load first page
            self.load_channel_page(None)
        except Exception:
            pass

    def load_channel_page(self, page_token: Optional[str]) -> None:
        api_key = get_youtube_api_key()
        cid = self._channel_ctx.get("channel_id")
        if not api_key or not cid:
            return
        cache = self._channel_ctx.get("cache") or {}
        cache_key = page_token
        cached = cache.get(cache_key)
        if cached:
            items, next_token = cached
            logging.warning(
                "Load channel page from cache: id=%s token=%s items=%d next=%s",
                cid,
                page_token,
                len(items or []),
                bool(next_token),
            )
        else:
            try:
                logging.warning("Fetch channel page: id=%s token=%s", cid, page_token)
                items, next_token = list_channel_videos(api_key, cid, max_results=25, page_token=page_token)
            except Exception as e:
                logging.exception("Error fetching channel page: %s", e)
                items, next_token = [], None
            # Cache the result
            try:
                cache[cache_key] = (items, next_token)
                self._channel_ctx["cache"] = cache
            except Exception:
                pass
        # Update tokens
        self._channel_ctx["current_token"] = page_token
        self._channel_ctx["next_token"] = next_token
        # Update UI controls state
        try:
            has_prev = bool(self._channel_ctx.get("prev_tokens"))
            self.main.btn_prev_page.setVisible(True)
            self.main.btn_prev_page.setEnabled(has_prev)
            self.main.btn_next_page.setVisible(True)
            self.main.btn_next_page.setEnabled(bool(next_token))
        except Exception:
            pass
        # Populate videos
        logging.warning("Channel page loaded: items=%d next_token=%s", len(items), bool(next_token))
        self.main._found_items = items  # stash for add/play
        self.main._populate_results(items)
        if not items:
            try:
                QMessageBox.information(self.main, "Channel", "No videos found for this channel or request failed.")
            except Exception:
                pass

    def on_channel_next_page(self) -> None:
        try:
            cur = self._channel_ctx.get("current_token")
            nxt = self._channel_ctx.get("next_token")
            if not nxt:
                return
            self._channel_ctx["prev_tokens"].append(cur)
            self.load_channel_page(nxt)
        except Exception:
            pass

    def on_channel_prev_page(self) -> None:
        try:
            prev_stack = self._channel_ctx.get("prev_tokens") or []
            if not prev_stack:
                return
            prev_token = prev_stack.pop()
            self._channel_ctx["prev_tokens"] = prev_stack
            self.load_channel_page(prev_token)
        except Exception:
            pass

    def on_back_to_channels(self) -> None:
        try:
            logging.warning("Back to channel search results")
            channels = getattr(self.main, "_found_channels", [])
            self.populate_channel_results(channels)
        except Exception:
            pass

    def on_save_all_results(self) -> None:
        """Save videos from current channel view: supports saving first N pages."""
        try:
            cid = self._channel_ctx.get("channel_id")
            if not cid:
                QMessageBox.information(self.main, "Save", "Not in a channel videos view.")
                return
            api_key = get_youtube_api_key()
            if not api_key:
                QMessageBox.information(self.main, "YouTube API Key", "Configure YOUTUBE_API_KEY in .env.")
                return
            # Prompt for playlist name
            default_name = (self._channel_ctx.get("channel_name") or "Channel Videos").strip() or "Channel Videos"
            from PySide6.QtWidgets import QInputDialog, QLineEdit
            new_name, ok = QInputDialog.getText(self.main, "New Playlist Name", "Name", QLineEdit.Normal, default_name)
            if not ok or not new_name.strip():
                return
            new_name = new_name.strip()
            if new_name in self.main.pm.names:
                QMessageBox.warning(self.main, "Exists", f"Playlist '{new_name}' already exists.")
                return
            # Determine how many pages have been visited (and cached)
            prev_tokens = list(self._channel_ctx.get("prev_tokens") or [])
            current_token = self._channel_ctx.get("current_token")
            visited_pages = len(prev_tokens) + 1  # include current page
            # Prompt: save N pages starting from the first visited page
            pages, ok_pages = QInputDialog.getInt(
                self.main,
                "Pages",
                f"Save how many pages? (visited: {visited_pages})",
                visited_pages,
                1,
                max(1, visited_pages),
                1,
            )
            if not ok_pages:
                return
            # Collect items strictly from visited pages starting at the first page
            all_items = []
            cache = self._channel_ctx.get("cache") or {}
            pages_remaining = pages
            # 1) earliest-to-latest visited pages before current
            for tok in prev_tokens:
                if pages_remaining <= 0:
                    break
                try:
                    cached = cache.get(tok)
                    if cached:
                        page_items, _nt = cached
                        all_items.extend(page_items or [])
                        pages_remaining -= 1
                except Exception as e:
                    logging.exception("Error reading cached prev page while saving: %s", e)
            # 2) include current page
            if pages_remaining > 0:
                current_items = getattr(self.main, "_found_items", [])
                all_items.extend(current_items or [])
                pages_remaining -= 1
            # Create playlist and persist
            self.main.pm.create(new_name)
            for it in all_items:
                self.main.pm.add(new_name, it)
            self.main.playlists.addItem(new_name)
            QMessageBox.information(self.main, "Saved", f"Saved {len(all_items)} videos to '{new_name}'.")
        except Exception as e:
            logging.exception("Save all results failed: %s", e)
            try:
                QMessageBox.warning(self.main, "Save", "Failed to save videos. See logs for details.")
            except Exception:
                pass
