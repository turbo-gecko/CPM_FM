from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPalette
from PySide6.QtWidgets import QScrollArea, QWidget

from cpm_fm.terminal.vt100_engine import Cell, VT100Engine

# Navigation / editing / function keys -> VT-100 byte sequences. Arrow keys use
# the normal-mode CSI form (ESC[A..D); the engine does not track application-
# cursor-key mode (DECCKM), so the normal form is always sent.
_SPECIAL_KEYS: dict[Qt.Key, bytes] = {
    Qt.Key.Key_Up: b"\x1b[A",
    Qt.Key.Key_Down: b"\x1b[B",
    Qt.Key.Key_Right: b"\x1b[C",
    Qt.Key.Key_Left: b"\x1b[D",
    Qt.Key.Key_Home: b"\x1b[H",
    Qt.Key.Key_End: b"\x1b[F",
    Qt.Key.Key_PageUp: b"\x1b[5~",
    Qt.Key.Key_PageDown: b"\x1b[6~",
    Qt.Key.Key_Insert: b"\x1b[2~",
    Qt.Key.Key_Delete: b"\x1b[3~",
    Qt.Key.Key_Escape: b"\x1b",
    Qt.Key.Key_Tab: b"\t",
    Qt.Key.Key_Backtab: b"\x1b[Z",
    Qt.Key.Key_Backspace: b"\x08",
    Qt.Key.Key_F1: b"\x1bOP",
    Qt.Key.Key_F2: b"\x1bOQ",
    Qt.Key.Key_F3: b"\x1bOR",
    Qt.Key.Key_F4: b"\x1bOS",
    Qt.Key.Key_F5: b"\x1b[15~",
    Qt.Key.Key_F6: b"\x1b[17~",
    Qt.Key.Key_F7: b"\x1b[18~",
    Qt.Key.Key_F8: b"\x1b[19~",
    Qt.Key.Key_F9: b"\x1b[20~",
    Qt.Key.Key_F10: b"\x1b[21~",
    Qt.Key.Key_F11: b"\x1b[23~",
    Qt.Key.Key_F12: b"\x1b[24~",
}

# Ctrl + these punctuation keys -> the C0 control byte they name.
_CTRL_PUNCT: dict[Qt.Key, int] = {
    Qt.Key.Key_BracketLeft: 0x1B,  # Ctrl-[  = ESC
    Qt.Key.Key_Backslash: 0x1C,  # Ctrl-\
    Qt.Key.Key_BracketRight: 0x1D,  # Ctrl-]
    Qt.Key.Key_Space: 0x00,  # Ctrl-Space = NUL
}


def encode_key(
    key: int, modifiers: Qt.KeyboardModifier, text: str, eol: bytes = b"\r"
) -> bytes | None:
    """Translate a key press to the bytes to transmit, or None if nothing.

    Handles Enter (the configured ``eol``), navigation/function keys (VT-100
    sequences), Ctrl-letter / Ctrl-punctuation control bytes, and otherwise the
    typed character(s). Replaces the former transmit-field parsing.

    Satisfies: FR-096, FR-094, FR-158.
    """
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        return eol
    special = _SPECIAL_KEYS.get(Qt.Key(key)) if _is_key(key) else None
    if special is not None:
        return special
    ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
    if ctrl and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return bytes([key - Qt.Key.Key_A + 1])
    if ctrl and _is_key(key):
        punct = _CTRL_PUNCT.get(Qt.Key(key))
        if punct is not None:
            return bytes([punct])
    if text:
        if len(text) == 1 and ord(text) < 0x20:
            # A control character Qt already resolved (e.g. some Ctrl combos).
            return text.encode("latin-1")
        return text.encode("utf-8")
    return None


def _is_key(key: int) -> bool:
    """True if ``key`` is a defined Qt.Key value (guards Qt.Key() conversion)."""
    try:
        Qt.Key(key)
        return True
    except ValueError:
        return False


# Minimum usable grid the reflow will not shrink below (FR-091a).
_MIN_COLS = 20
_MIN_ROWS = 5


def grid_size_for(width: int, height: int, cell_w: int, cell_h: int) -> tuple[int, int]:
    """Columns and rows that fit a ``width`` x ``height`` viewport in pixels.

    Pure geometry for the terminal reflow: the visible cell counts are the
    whole cells that fit the viewport, clamped to a minimum usable grid so a
    very small window never collapses the emulator to a degenerate size.

    Satisfies: FR-091a.
    """
    cols = max(_MIN_COLS, width // max(1, cell_w))
    rows = max(_MIN_ROWS, height // max(1, cell_h))
    return cols, rows


# Map pyte's ANSI colour names to concrete RGB. Names not found here (notably
# "default", and 256-/true-colour hex strings) are resolved in _colour().
_ANSI_COLOURS: dict[str, QColor] = {
    "black": QColor(0, 0, 0),
    "red": QColor(205, 0, 0),
    "green": QColor(0, 205, 0),
    "brown": QColor(205, 205, 0),
    "yellow": QColor(205, 205, 0),
    "blue": QColor(0, 0, 238),
    "magenta": QColor(205, 0, 205),
    "cyan": QColor(0, 205, 205),
    "white": QColor(229, 229, 229),
    "brightblack": QColor(127, 127, 127),
    "brightred": QColor(255, 0, 0),
    "brightgreen": QColor(0, 255, 0),
    "brightbrown": QColor(255, 255, 0),
    "brightyellow": QColor(255, 255, 0),
    "brightblue": QColor(92, 92, 255),
    "brightmagenta": QColor(255, 0, 255),
    "brightcyan": QColor(0, 255, 255),
    "brightwhite": QColor(255, 255, 255),
}


class _TerminalGrid(QWidget):
    """Inner canvas of :class:`TerminalView` that paints the character grid.

    A fixed-size widget (cols x total-rows cells) hosted inside the scroll area,
    so the scroll bars page through scrollback; painting is delegated back to the
    owning view, which owns the engine and cell metrics.

    Satisfies: UIR-061, UIR-062.
    """

    def __init__(self, view: TerminalView) -> None:
        super().__init__(view)
        self._view = view

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Satisfies: FR-091, UIR-061."""
        self._view._paint_grid(self, event.rect())


class TerminalView(QScrollArea):
    """VT-100 screen renderer: a monospaced character grid over a VT100Engine.

    Replaces the former plain-text receive area (UIR-061). Received bytes are
    interpreted by the engine (fed on the GUI thread); this widget renders the
    resulting screen — cursor, SGR attributes, and ANSI colour — plus the
    scrollback that has rolled off the top, with autoscroll following new output
    when enabled (UIR-062/UIR-066).

    Satisfies: FR-091, UIR-061, UIR-062.
    """

    def __init__(self, engine: VT100Engine, parent: QWidget | None = None) -> None:
        """Satisfies: FR-091, UIR-061, UIR-063."""
        super().__init__(parent)
        self._engine = engine
        self._autoscroll = True
        # FR-096: keystrokes typed here are encoded and passed to this callback
        # for transmission on the Terminal Port. FR-094: Enter transmits the EOL.
        self._key_callback: Callable[[bytes], None] | None = None
        self._eol = b"\r"
        # Accept keyboard focus so the operator can type into the terminal.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        font = QFont("Courier New")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._font = font
        fm = QFontMetrics(font)
        self._cell_w = max(1, fm.horizontalAdvance("M"))
        self._cell_h = max(1, fm.height())
        self._ascent = fm.ascent()

        self._grid = _TerminalGrid(self)
        self._grid.setFont(font)
        self.setWidget(self._grid)
        self.setWidgetResizable(False)
        # Terminal-like background for the area outside the fixed grid.
        self.viewport().setAutoFillBackground(True)
        self.refresh()

    # -------------------------------------------------------------- public API

    def set_engine(self, engine: VT100Engine) -> None:
        """Point the view at a different engine and repaint.

        Satisfies: FR-091.
        """
        self._engine = engine
        self.refresh()

    def set_key_callback(self, callback: Callable[[bytes], None] | None) -> None:
        """Set the sink for encoded keystroke bytes (FR-096).

        Satisfies: FR-096.
        """
        self._key_callback = callback

    def set_eol(self, eol: bytes) -> None:
        """Set the bytes the Enter key transmits (the configured EOL, FR-094).

        Satisfies: FR-094.
        """
        self._eol = eol

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        """Encode the key press and send it to the Terminal Port (FR-096).

        Keys that map to bytes are sent and the event is accepted (so, e.g.,
        arrow keys are transmitted rather than scrolling the view). Anything
        unmapped falls through to the base class.

        Satisfies: FR-096, FR-094, FR-158, UIR-063.
        """
        data = encode_key(event.key(), event.modifiers(), event.text(), self._eol)
        if data and self._key_callback is not None:
            self._key_callback(data)
            event.accept()
            return
        super().keyPressEvent(event)

    def set_autoscroll(self, enabled: bool) -> None:
        """Enable/disable following new output to the bottom (UIR-066).

        Satisfies: UIR-062, UIR-066.
        """
        self._autoscroll = enabled
        if enabled:
            self._scroll_to_bottom()
        self._grid.update()

    def refresh(self) -> None:
        """Resize the grid to the current content and repaint (UIR-062).

        Called after the engine has been fed. Grows the canvas as scrollback
        accumulates and, when autoscroll is on, keeps the newest output visible.

        Satisfies: FR-091, UIR-062.
        """
        width = self._engine.cols * self._cell_w
        height = self._total_rows() * self._cell_h
        self._grid.setFixedSize(width, height)
        if self._autoscroll:
            self._scroll_to_bottom()
        self._grid.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Reflow the emulator grid to the new window size (FR-091a).

        Only a visible view reflows; a hidden view (e.g. under test, before the
        Terminal Window is shown) keeps its engine geometry untouched.

        Satisfies: FR-091a.
        """
        super().resizeEvent(event)
        if self.isVisible():
            self._reflow_to_viewport()

    def _reflow_to_viewport(self) -> None:
        """Resize the engine to the columns/rows that fit the viewport.

        The remote is not notified — the serial link has no terminal-size
        negotiation channel (FR-091a).

        Satisfies: FR-091a.
        """
        vp = self.viewport().size()
        cols, rows = grid_size_for(vp.width(), vp.height(), self._cell_w, self._cell_h)
        if (cols, rows) != (self._engine.cols, self._engine.rows):
            self._engine.resize(cols, rows)
        self.refresh()

    # ---------------------------------------------------------------- internals

    def _total_rows(self) -> int:
        """Scrollback lines plus the live screen rows."""
        return self._engine.history_len + self._engine.rows

    def _scroll_to_bottom(self) -> None:
        vbar = self.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def _row_cells(self, row: int) -> list[Cell] | None:
        """Cells for absolute row ``row`` (scrollback first, then live screen)."""
        hlen = self._engine.history_len
        if row < hlen:
            return self._engine.history_line(row)
        active = row - hlen
        if 0 <= active < self._engine.rows:
            return self._engine.line(active)
        return None

    @staticmethod
    def _colour(name: str, default: QColor) -> QColor:
        """Resolve a pyte colour name to a QColor ("default"/unknown -> default).

        Satisfies: FR-091, FR-157c.
        """
        if name == "default":
            return default
        mapped = _ANSI_COLOURS.get(name)
        if mapped is not None:
            return mapped
        if len(name) == 6:  # 256-/true-colour as a 6-hex string
            try:
                return QColor(int(name[0:2], 16), int(name[2:4], 16), int(name[4:6], 16))
            except ValueError:
                pass
        return default

    def _paint_grid(self, widget: QWidget, rect) -> None:
        """Paint the rows intersecting ``rect`` (called from the grid's paint).

        Satisfies: FR-091, UIR-061.
        """
        painter = QPainter(widget)
        painter.setFont(self._font)
        pal = self.palette()
        default_bg = pal.color(QPalette.ColorRole.Base)
        default_fg = pal.color(QPalette.ColorRole.Text)
        painter.fillRect(rect, default_bg)

        cw, ch = self._cell_w, self._cell_h
        first = max(0, rect.top() // ch)
        last = min(self._total_rows() - 1, rect.bottom() // ch)

        for row in range(first, last + 1):
            cells = self._row_cells(row)
            if cells is None:
                continue
            y = row * ch
            for col, cell in enumerate(cells):
                fg = self._colour(cell.fg, default_fg)
                bg = self._colour(cell.bg, default_bg)
                if cell.reverse:
                    fg, bg = bg, fg
                x = col * cw
                if bg != default_bg:
                    painter.fillRect(x, y, cw, ch, bg)
                if cell.char and cell.char != " ":
                    f = self._font
                    if cell.bold or cell.underscore or cell.italics:
                        f = QFont(self._font)
                        f.setBold(cell.bold)
                        f.setUnderline(cell.underscore)
                        f.setItalic(cell.italics)
                    painter.setFont(f)
                    painter.setPen(fg)
                    painter.drawText(x, y + self._ascent, cell.char)

        self._paint_cursor(painter, first, last, default_fg, default_bg)

    def _paint_cursor(
        self, painter: QPainter, first: int, last: int, default_fg: QColor, default_bg: QColor
    ) -> None:
        """Draw a block cursor at the live-screen cursor cell, if visible.

        Satisfies: FR-091.
        """
        if self._engine.cursor_hidden:
            return
        cx, cy = self._engine.cursor
        row = self._engine.history_len + cy
        if not (first <= row <= last) or not (0 <= cx < self._engine.cols):
            return
        cw, ch = self._cell_w, self._cell_h
        x, y = cx * cw, row * ch
        painter.fillRect(x, y, cw, ch, default_fg)
        cells = self._engine.line(cy)
        cell = cells[cx] if cx < len(cells) else None
        if cell and cell.char and cell.char != " ":
            painter.setFont(self._font)
            painter.setPen(default_bg)
            painter.drawText(x, y + self._ascent, cell.char)
