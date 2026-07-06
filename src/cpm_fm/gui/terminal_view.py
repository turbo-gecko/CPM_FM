from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from cpm_fm.terminal.term_translate import ADM3A, VT52
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

# Terminal-type cursor-key overrides (FR-158a/FR-158b). Only the keys that
# differ from the VT-100 mapping are listed; any key not here falls through to
# the VT-100 encoding below.
_VT52_KEYS: dict[Qt.Key, bytes] = {
    Qt.Key.Key_Up: b"\x1bA",
    Qt.Key.Key_Down: b"\x1bB",
    Qt.Key.Key_Right: b"\x1bC",
    Qt.Key.Key_Left: b"\x1bD",
}
_ADM3A_KEYS: dict[Qt.Key, bytes] = {
    Qt.Key.Key_Up: b"\x0b",  # Ctrl-K
    Qt.Key.Key_Down: b"\x0a",  # Ctrl-J
    Qt.Key.Key_Left: b"\x08",  # Ctrl-H
    Qt.Key.Key_Right: b"\x0c",  # Ctrl-L
    Qt.Key.Key_Home: b"\x1e",  # RS
}
_TERMINAL_KEY_OVERRIDES: dict[str, dict[Qt.Key, bytes]] = {
    VT52: _VT52_KEYS,
    ADM3A: _ADM3A_KEYS,
}


def encode_key(
    key: int,
    modifiers: Qt.KeyboardModifier,
    text: str,
    eol: bytes = b"\r",
    terminal_type: str = "VT100",
) -> bytes | None:
    """Translate a key press to the bytes to transmit, or None if nothing.

    Handles Enter (the configured ``eol``), navigation/function keys (VT-100
    sequences), Ctrl-letter / Ctrl-punctuation control bytes, and otherwise the
    typed character(s). Replaces the former transmit-field parsing.

    ``terminal_type`` selects the cursor-key encoding: VT-52 (FR-158a) and
    ADM-3A (FR-158b) override the arrow keys (and, for ADM-3A, Home); every
    other key uses the VT-100 mapping regardless of type.

    Satisfies: FR-096, FR-094, FR-158, FR-158a, FR-158b.
    """
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        return eol
    if _is_key(key):
        override = _TERMINAL_KEY_OVERRIDES.get(terminal_type, {}).get(Qt.Key(key))
        if override is not None:
            return override
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

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        """Begin a text selection on a left-button press (UIR-100)."""
        p = event.position().toPoint()
        self._view._mouse_press(p.x(), p.y(), event.button())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        """Extend the in-progress selection as the mouse is dragged (UIR-100)."""
        p = event.position().toPoint()
        self._view._mouse_move(p.x(), p.y())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        """Finish the selection on button release (UIR-100)."""
        p = event.position().toPoint()
        self._view._mouse_release(p.x(), p.y(), event.button())

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802 (Qt override)
        """Delegate the right-click context menu to the owning view (UIR-099)."""
        self._view._context_menu(event.globalPos())


class TerminalView(QScrollArea):
    """VT-100 screen renderer: a monospaced character grid over a VT100Engine.

    Replaces the former plain-text receive area (UIR-061). Received bytes are
    interpreted by the engine (fed on the GUI thread); this widget renders the
    resulting screen — cursor, SGR attributes, and ANSI colour — plus the
    scrollback that has rolled off the top, with autoscroll following new output
    when enabled (UIR-062/UIR-066).

    Satisfies: FR-091, UIR-061, UIR-062.
    """

    def __init__(
        self, engine: VT100Engine, parent: QWidget | None = None, font: QFont | None = None
    ) -> None:
        """Satisfies: FR-091, UIR-061, UIR-063, UIR-069.

        ``font`` sets the initial Receive-view font; when omitted a monospaced
        Courier New is used (UIR-069).
        """
        super().__init__(parent)
        self._engine = engine
        self._autoscroll = True
        # FR-096: keystrokes typed here are encoded and passed to this callback
        # for transmission on the Terminal Port. FR-094: Enter transmits the EOL.
        self._key_callback: Callable[[bytes], None] | None = None
        self._eol = b"\r"
        # UIR-100: mouse text-selection state, as absolute (row, col) cell
        # coordinates spanning scrollback + live screen. None when nothing is
        # selected; _selecting is True only during an active click-drag.
        self._sel_anchor: tuple[int, int] | None = None
        self._sel_end: tuple[int, int] | None = None
        self._selecting = False
        # UIR-099: invoked with a global QPoint when the view is right-clicked,
        # so the owner can build and show the context menu.
        self._context_menu_cb: Callable[[QPoint], None] | None = None
        # Accept keyboard focus so the operator can type into the terminal.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        if font is None:
            font = QFont("Courier New")
            font.setStyleHint(QFont.StyleHint.Monospace)
        self._grid = _TerminalGrid(self)
        self._apply_font(font)
        self.setWidget(self._grid)
        self.setWidgetResizable(False)
        # Terminal-like background for the area outside the fixed grid.
        self.viewport().setAutoFillBackground(True)
        self.refresh()

    def _apply_font(self, font: QFont) -> None:
        """Store ``font`` and recompute the cell metrics it implies (UIR-069).

        Shared by construction and :meth:`set_font`: the cell width/height and
        text baseline all derive from the font's :class:`QFontMetrics`, so they
        must be recomputed together whenever the font changes.

        Satisfies: FR-091, UIR-069.
        """
        self._font = font
        fm = QFontMetrics(font)
        self._cell_w = max(1, fm.horizontalAdvance("M"))
        self._cell_h = max(1, fm.height())
        self._ascent = fm.ascent()
        self._grid.setFont(font)

    # -------------------------------------------------------------- public API

    def set_font(self, font: QFont) -> None:
        """Change the Receive-view font and reflow the grid to the new metrics.

        The cell size derives from the font, so the emulator grid is reflowed to
        the columns/rows that now fit the viewport (FR-091a) and repainted.

        Satisfies: UIR-069, FR-091a.
        """
        self._apply_font(font)
        if self.isVisible():
            self._reflow_to_viewport()
        self.refresh()

    def current_font(self) -> QFont:
        """The Receive-view's current font (used to seed the font dialog).

        Satisfies: UIR-069.
        """
        return QFont(self._font)

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

    def set_context_menu_callback(self, callback: Callable[[QPoint], None] | None) -> None:
        """Set the handler invoked (with a global QPoint) on a right-click.

        The owner (Terminal Window) builds and shows the context menu; the view
        only reports where the click occurred (UIR-099).

        Satisfies: UIR-099.
        """
        self._context_menu_cb = callback

    def has_selection(self) -> bool:
        """Whether any text is currently highlighted (backs Copy's enabled state).

        Satisfies: FR-165, UIR-100.
        """
        return self._selection_range() is not None

    def selected_text(self) -> str:
        """The highlighted text: selected cells row by row, trailing blanks
        trimmed per row, rows joined by a single newline (FR-165).

        Returns an empty string when nothing is selected.

        Satisfies: FR-165, UIR-100.
        """
        rng = self._selection_range()
        if rng is None:
            return ""
        (r0, c0), (r1, c1) = rng
        lines: list[str] = []
        for row in range(r0, r1 + 1):
            cells = self._row_cells(row)
            if cells is None:
                lines.append("")
                continue
            start = c0 if row == r0 else 0
            end = c1 if row == r1 else len(cells)
            chars = "".join((cell.char or " ") for cell in cells[start:end])
            lines.append(chars.rstrip())
        return "\n".join(lines)

    def copy_selection(self) -> None:
        """Copy the highlighted text to the system clipboard (FR-165).

        A no-op when nothing is selected.

        Satisfies: FR-165.
        """
        text = self.selected_text()
        if text:
            QApplication.clipboard().setText(text)

    def clear_selection(self) -> None:
        """Drop any current selection and repaint (e.g. on Clear/reset).

        Satisfies: UIR-100.
        """
        self._sel_anchor = None
        self._sel_end = None
        self._selecting = False
        self._grid.update()

    def viewport_size_for(self, cols: int, rows: int) -> QSize:
        """Pixel size of a viewport that holds exactly ``cols`` x ``rows`` cells.

        Backs the Terminal Window's Reset-Size action (FR-167): the window resizes
        so its Receive-view viewport becomes this size, and the reflow (FR-091a)
        then settles the grid to the requested geometry.

        Satisfies: FR-167.
        """
        return QSize(cols * self._cell_w, rows * self._cell_h)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        """Encode the key press and send it to the Terminal Port (FR-096).

        Keys that map to bytes are sent and the event is accepted (so, e.g.,
        arrow keys are transmitted rather than scrolling the view). Anything
        unmapped falls through to the base class.

        Satisfies: FR-096, FR-094, FR-158, FR-158a, FR-158b, UIR-063.
        """
        data = encode_key(
            event.key(),
            event.modifiers(),
            event.text(),
            self._eol,
            self._engine.terminal_type,
        )
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
            # Row/column indices shift on a reflow, so any selection is stale.
            self._sel_anchor = self._sel_end = None
            self._selecting = False
            self._engine.resize(cols, rows)
        self.refresh()

    # ------------------------------------------------------------ mouse/selection

    def _mouse_press(self, x: int, y: int, button: Qt.MouseButton) -> None:
        """Start a selection at the clicked cell on a left-button press (UIR-100).

        Satisfies: UIR-100.
        """
        if button == Qt.MouseButton.LeftButton:
            self._sel_anchor = self._cell_at(x, y)
            self._sel_end = self._sel_anchor
            self._selecting = True
            self._grid.update()

    def _mouse_move(self, x: int, y: int) -> None:
        """Extend the active selection to the current cell (UIR-100).

        Satisfies: UIR-100.
        """
        if self._selecting:
            self._sel_end = self._cell_at(x, y)
            self._grid.update()

    def _mouse_release(self, x: int, y: int, button: Qt.MouseButton) -> None:
        """Finish the selection; a click with no drag clears it (UIR-100).

        Satisfies: UIR-100.
        """
        if button == Qt.MouseButton.LeftButton and self._selecting:
            self._sel_end = self._cell_at(x, y)
            self._selecting = False
            if self._sel_anchor == self._sel_end:
                self._sel_anchor = self._sel_end = None
            self._grid.update()

    def _context_menu(self, global_pos: QPoint) -> None:
        """Report a right-click to the owner so it can show the menu (UIR-099).

        Satisfies: UIR-099.
        """
        if self._context_menu_cb is not None:
            self._context_menu_cb(global_pos)

    def _cell_at(self, x: int, y: int) -> tuple[int, int]:
        """Map a grid-local pixel position to a clamped (row, col) cell.

        Column is clamped to ``0..cols`` (``cols`` meaning past the last cell, so
        a drag to a line's end selects the whole line); row to the painted range.

        Satisfies: UIR-100.
        """
        row = max(0, min(y // self._cell_h, self._total_rows() - 1))
        col = max(0, min(x // self._cell_w, self._engine.cols))
        return row, col

    def _selection_range(
        self,
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """Normalised (start, end) selection in reading order, or None if empty.

        Satisfies: FR-165, UIR-100.
        """
        if self._sel_anchor is None or self._sel_end is None:
            return None
        a, b = self._sel_anchor, self._sel_end
        if a == b:
            return None
        return (a, b) if a <= b else (b, a)

    @staticmethod
    def _is_selected(
        row: int, col: int, rng: tuple[tuple[int, int], tuple[int, int]] | None
    ) -> bool:
        """Whether cell (row, col) falls inside the stream selection ``rng``.

        Satisfies: UIR-100.
        """
        if rng is None:
            return False
        (r0, c0), (r1, c1) = rng
        if row < r0 or row > r1:
            return False
        if r0 == r1:
            return c0 <= col < c1
        if row == r0:
            return col >= c0
        if row == r1:
            return col < c1
        return True

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

        Satisfies: FR-091, UIR-061, UIR-100.
        """
        painter = QPainter(widget)
        painter.setFont(self._font)
        pal = self.palette()
        default_bg = pal.color(QPalette.ColorRole.Base)
        default_fg = pal.color(QPalette.ColorRole.Text)
        # UIR-100: palette colours for highlighted (selected) cells.
        sel_bg = pal.color(QPalette.ColorRole.Highlight)
        sel_fg = pal.color(QPalette.ColorRole.HighlightedText)
        rng = self._selection_range()
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
                # UIR-100: selected cells override colour with the highlight pair.
                selected = self._is_selected(row, col, rng)
                if selected:
                    fg, bg = sel_fg, sel_bg
                x = col * cw
                if selected or bg != default_bg:
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
