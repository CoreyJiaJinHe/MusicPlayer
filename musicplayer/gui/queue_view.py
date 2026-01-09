from typing import List, Callable
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QPushButton, QWidget, QScrollArea, QHBoxLayout, QSizePolicy


class QueueViewController:
    """Controller to render and manage the horizontally scrollable queue view."""

    def __init__(
        self,
        scroll_area: QScrollArea,
        layout: QHBoxLayout,
        toggle_button: QPushButton,
        load_thumb: Callable[[str, QLabel], None],
    ) -> None:
        self._scroll = scroll_area
        self._layout = layout
        self._toggle_btn = toggle_button
        self._load_thumb = load_thumb
        self._card_widgets: List[QWidget] = []
        self._play_handler: Callable[[int], None] = lambda idx: None

    def set_play_handler(self, fn: Callable[[int], None]) -> None:
        self._play_handler = fn

    def toggle_view(self) -> None:
        try:
            visible = self._toggle_btn.isChecked()
            self._scroll.setVisible(visible)
            self._toggle_btn.setText("Hide Queue" if visible else "Show Queue")
        except Exception:
            pass

    def refresh(
        self,
        queue_items: List[object],
        queue_index: int,
        shuffled_indices: List[int],
        shuffle_enabled: bool,
        auto_scroll: bool,
    ) -> None:
        """Rebuild queue cards using provided state and optionally auto-scroll."""
        try:
            # Clear existing cards
            while self._layout.count():
                item = self._layout.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)

            # Determine display order
            if shuffle_enabled and shuffled_indices:
                display_indices = list(shuffled_indices)
            else:
                display_indices = list(range(len(queue_items)))

            self._card_widgets = []
            for pos, idx in enumerate(display_indices):
                it = queue_items[idx]
                btn = QPushButton()
                btn.setCheckable(False)
                btn.setFlat(False)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setFixedSize(140, 150)

                card_w = QWidget()
                from PySide6.QtWidgets import QVBoxLayout
                v = QVBoxLayout(card_w)
                v.setContentsMargins(4, 4, 4, 4)
                thumb = QLabel()
                thumb.setFixedSize(120, 72)
                thumb.setAlignment(Qt.AlignCenter)
                thumb.setStyleSheet("background:transparent;")
                title = QLabel(getattr(it, 'title', ''))
                title.setWordWrap(True)
                title.setFixedWidth(120)
                title.setStyleSheet("font-size:11px;")
                v.addWidget(thumb, alignment=Qt.AlignCenter)
                v.addWidget(title, alignment=Qt.AlignCenter)
                from PySide6.QtWidgets import QVBoxLayout as _VL
                btn.setLayout(_VL())
                btn.layout().addWidget(card_w)
                try:
                    if getattr(it, 'thumbnail_url', None):
                        self._load_thumb(getattr(it, 'thumbnail_url'), thumb)
                except Exception:
                    pass

                # Color by position relative to current displayed position
                try:
                    pos_current = None
                    if queue_index in display_indices:
                        pos_current = display_indices.index(queue_index)
                    if pos_current is not None:
                        if pos == pos_current:
                            color = '#d4ffd9'
                        elif pos < pos_current:
                            color = '#ffd6d6'
                        else:
                            color = '#d6e7ff'
                    else:
                        if queue_index == idx:
                            color = '#d4ffd9'
                        elif queue_index >= 0 and idx < queue_index:
                            color = '#ffd6d6'
                        else:
                            color = '#d6e7ff'
                    btn.setStyleSheet(f'background-color: {color}; border-radius:6px;')
                except Exception:
                    pass

                btn.clicked.connect(lambda _, i=idx: self._play_handler(i))
                self._layout.addWidget(btn)
                self._card_widgets.append(btn)

            # Auto-scroll to current card if enabled
            try:
                if auto_scroll and queue_index >= 0 and self._card_widgets and queue_index in display_indices:
                    pos_current = display_indices.index(queue_index)
                    widget = self._card_widgets[pos_current]

                    def _do_scroll():
                        try:
                            viewport = self._scroll.viewport()
                            sb = self._scroll.horizontalScrollBar()
                            x = widget.x()
                            w = widget.width()
                            vp_w = viewport.width()
                            target = max(0, x - (vp_w - w) // 2)
                            sb.setValue(target)
                        except Exception:
                            try:
                                self._scroll.ensureWidgetVisible(widget)
                            except Exception:
                                pass

                    QTimer.singleShot(50, _do_scroll)
            except Exception:
                pass
        except Exception:
            pass

    def scroll_to_index(self, queue_items: List[object], queue_index: int, shuffled_indices: List[int], shuffle_enabled: bool) -> None:
        try:
            if not self._card_widgets or queue_index < 0 or queue_index >= len(queue_items):
                return
            if shuffle_enabled and shuffled_indices:
                display_indices = list(shuffled_indices)
            else:
                display_indices = list(range(len(queue_items)))
            if queue_index not in display_indices:
                return
            pos = display_indices.index(queue_index)
            widget = self._card_widgets[pos]
            try:
                self._scroll.ensureWidgetVisible(widget)
            except Exception:
                try:
                    sb = self._scroll.horizontalScrollBar()
                    x = widget.x()
                    sb.setValue(x)
                except Exception:
                    pass
        except Exception:
            pass
