from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QScrollArea, QWidget

from cpm_fm.terminal.vt100_engine import Cell, VT100Engine

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
        """Satisfies: FR-091, UIR-061."""
        super().__init__(parent)
        self._engine = engine
        self._autoscroll = True

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

        Satisfies: FR-091.
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
