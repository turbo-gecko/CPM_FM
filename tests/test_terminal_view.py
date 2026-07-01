"""Tests for the VT-100 grid renderer (TerminalView).

Headless under the offscreen Qt platform. These assert the model-facing
behaviour (row selection across scrollback/live screen, colour mapping,
autoscroll, grid sizing) and that painting the grid offscreen does not raise.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cpm_fm.gui.terminal_view import TerminalView  # noqa: E402
from cpm_fm.terminal.vt100_engine import VT100Engine  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_colour_default_and_named_and_hex():
    """Verifies: FR-091."""
    default = QColor(1, 2, 3)
    assert TerminalView._colour("default", default) == default
    assert TerminalView._colour("red", default) == QColor(205, 0, 0)
    assert TerminalView._colour("ff8800", default) == QColor(0xFF, 0x88, 0x00)
    # Unknown name falls back to the supplied default.
    assert TerminalView._colour("chartreuse", default) == default


def test_row_cells_spans_scrollback_then_live_screen(qapp):
    """Verifies: FR-091, UIR-062."""
    engine = VT100Engine(cols=10, rows=3, history=50)
    view = TerminalView(engine)
    try:
        for i in range(6):
            engine.feed(f"line{i}\r\n".encode())
        # 6 lines fed into a 3-row screen: the oldest rolled into scrollback.
        assert engine.history_len > 0
        # Absolute row 0 is the oldest scrollback line...
        first = "".join(c.char for c in view._row_cells(0)).rstrip()
        assert first == "line0"
        # ...and the last absolute row is on the live screen.
        total = engine.history_len + engine.rows
        assert view._row_cells(total - 1) is not None
        assert view._row_cells(total) is None  # past the end
    finally:
        view.deleteLater()


def test_grid_grows_with_scrollback(qapp):
    """Verifies: FR-091, UIR-062."""
    engine = VT100Engine(cols=10, rows=3, history=50)
    view = TerminalView(engine)
    try:
        h_before = view._grid.height()
        for i in range(10):
            engine.feed(f"row{i}\r\n".encode())
        view.refresh()
        assert view._grid.height() > h_before
    finally:
        view.deleteLater()


def test_autoscroll_toggle_moves_to_bottom(qapp):
    """Verifies: UIR-062, UIR-066."""
    engine = VT100Engine(cols=10, rows=3, history=200)
    view = TerminalView(engine)
    try:
        view.resize(120, 60)  # small viewport so content overflows
        for i in range(40):
            engine.feed(f"line{i}\r\n".encode())
        view.refresh()
        vbar = view.verticalScrollBar()
        assert vbar.value() == vbar.maximum()  # autoscroll follows to bottom

        # Turning autoscroll off and scrolling up stays put on refresh.
        view.set_autoscroll(False)
        vbar.setValue(0)
        engine.feed(b"more\r\n")
        view.refresh()
        assert vbar.value() == 0
    finally:
        view.deleteLater()


def test_paint_does_not_raise(qapp):
    """Verifies: FR-091."""
    engine = VT100Engine(cols=20, rows=4)
    view = TerminalView(engine)
    try:
        # Bold + reversed + coloured cell and a visible cursor exercise the
        # attribute/cursor paint paths.
        engine.feed(b"\x1b[1;7;31mX\x1b[0m plain")
        view.refresh()
        view._grid.grab()  # triggers paintEvent offscreen
    finally:
        view.deleteLater()
