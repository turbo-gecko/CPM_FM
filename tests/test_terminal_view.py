"""Tests for the VT-100 grid renderer (TerminalView).

Headless under the offscreen Qt platform. These assert the model-facing
behaviour (row selection across scrollback/live screen, colour mapping,
autoscroll, grid sizing) and that painting the grid offscreen does not raise.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cpm_fm.gui.terminal_view import TerminalView, encode_key, grid_size_for  # noqa: E402
from cpm_fm.terminal.vt100_engine import VT100Engine  # noqa: E402

_NONE = Qt.KeyboardModifier.NoModifier
_CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_encode_key_enter_uses_eol():
    """Verifies: FR-094, FR-096, FR-158."""
    assert encode_key(Qt.Key.Key_Return, _NONE, "\r", eol=b"\r\n") == b"\r\n"
    assert encode_key(Qt.Key.Key_Enter, _NONE, "", eol=b"\r") == b"\r"


def test_encode_key_printable_and_utf8():
    """Verifies: FR-096, FR-158."""
    assert encode_key(Qt.Key.Key_A, _NONE, "a") == b"a"
    assert encode_key(Qt.Key.Key_Space, _NONE, " ") == b" "
    assert encode_key(Qt.Key.Key_unknown, _NONE, "★") == "★".encode()


def test_encode_key_navigation_and_function_keys():
    """Verifies: FR-096, FR-158."""
    assert encode_key(Qt.Key.Key_Up, _NONE, "") == b"\x1b[A"
    assert encode_key(Qt.Key.Key_Down, _NONE, "") == b"\x1b[B"
    assert encode_key(Qt.Key.Key_Right, _NONE, "") == b"\x1b[C"
    assert encode_key(Qt.Key.Key_Left, _NONE, "") == b"\x1b[D"
    assert encode_key(Qt.Key.Key_Home, _NONE, "") == b"\x1b[H"
    assert encode_key(Qt.Key.Key_Delete, _NONE, "") == b"\x1b[3~"
    assert encode_key(Qt.Key.Key_F1, _NONE, "") == b"\x1bOP"
    assert encode_key(Qt.Key.Key_Escape, _NONE, "\x1b") == b"\x1b"
    assert encode_key(Qt.Key.Key_Tab, _NONE, "\t") == b"\t"
    assert encode_key(Qt.Key.Key_Backspace, _NONE, "\x08") == b"\x08"


def test_encode_key_vt52_arrows():
    """Verifies: FR-158a."""
    assert encode_key(Qt.Key.Key_Up, _NONE, "", terminal_type="VT52") == b"\x1bA"
    assert encode_key(Qt.Key.Key_Down, _NONE, "", terminal_type="VT52") == b"\x1bB"
    assert encode_key(Qt.Key.Key_Right, _NONE, "", terminal_type="VT52") == b"\x1bC"
    assert encode_key(Qt.Key.Key_Left, _NONE, "", terminal_type="VT52") == b"\x1bD"
    # Non-cursor keys still use the VT-100 encoding under VT-52.
    assert encode_key(Qt.Key.Key_F1, _NONE, "", terminal_type="VT52") == b"\x1bOP"
    assert encode_key(Qt.Key.Key_A, _NONE, "a", terminal_type="VT52") == b"a"


def test_encode_key_adm3a_arrows_and_home():
    """Verifies: FR-158b."""
    assert encode_key(Qt.Key.Key_Up, _NONE, "", terminal_type="ADM-3A") == b"\x0b"
    assert encode_key(Qt.Key.Key_Down, _NONE, "", terminal_type="ADM-3A") == b"\x0a"
    assert encode_key(Qt.Key.Key_Left, _NONE, "", terminal_type="ADM-3A") == b"\x08"
    assert encode_key(Qt.Key.Key_Right, _NONE, "", terminal_type="ADM-3A") == b"\x0c"
    assert encode_key(Qt.Key.Key_Home, _NONE, "", terminal_type="ADM-3A") == b"\x1e"
    # Other keys fall through to the VT-100 mapping (FR-158).
    assert encode_key(Qt.Key.Key_End, _NONE, "", terminal_type="ADM-3A") == b"\x1b[F"


def test_encode_key_default_type_is_vt100():
    """Verifies: FR-158, FR-158a, FR-158b."""
    # Without a terminal_type the arrow keys keep the VT-100 CSI form.
    assert encode_key(Qt.Key.Key_Up, _NONE, "") == b"\x1b[A"
    assert encode_key(Qt.Key.Key_Up, _NONE, "", terminal_type="VT100") == b"\x1b[A"


def test_encode_key_control_combinations():
    """Verifies: FR-096, FR-158."""
    assert encode_key(Qt.Key.Key_C, _CTRL, "") == b"\x03"  # Ctrl-C
    assert encode_key(Qt.Key.Key_A, _CTRL, "") == b"\x01"  # Ctrl-A
    assert encode_key(Qt.Key.Key_BracketLeft, _CTRL, "") == b"\x1b"  # Ctrl-[ = ESC
    assert encode_key(Qt.Key.Key_Space, _CTRL, "") == b"\x00"  # Ctrl-Space = NUL


def test_encode_key_returns_none_for_modifier_only():
    """Verifies: FR-096, FR-158."""
    # A bare modifier press (no text, not a mapped key) transmits nothing.
    assert encode_key(Qt.Key.Key_Shift, _NONE, "") is None


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


def test_grid_size_for_fits_cells_and_clamps_minimum():
    """Reflow geometry: whole cells that fit, clamped to a usable minimum.

    Verifies: FR-091a.
    """
    # 800x260 viewport at 10x13 cells -> 80 cols x 20 rows.
    assert grid_size_for(800, 260, 10, 13) == (80, 20)
    # A tiny viewport clamps to the 20x5 minimum rather than collapsing.
    assert grid_size_for(30, 20, 10, 13) == (20, 5)


def test_reflow_resizes_engine_to_viewport(qapp):
    """_reflow_to_viewport resizes the engine to the columns/rows that fit.

    Verifies: FR-091a.
    """
    engine = VT100Engine()
    view = TerminalView(engine)
    try:
        view.resize(400, 300)
        view._reflow_to_viewport()
        vp = view.viewport().size()
        exp = grid_size_for(vp.width(), vp.height(), view._cell_w, view._cell_h)
        assert (engine.cols, engine.rows) == exp
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


def test_constructor_accepts_font(qapp):
    """A font passed to the constructor is honoured by current_font.

    Verifies: UIR-069.
    """
    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine, font=QFont("Courier New", 18))
    try:
        assert view.current_font().pointSize() == 18
    finally:
        view.deleteLater()


def test_set_font_updates_cell_metrics_and_paints(qapp):
    """set_font recomputes the cell metrics and the grid still paints.

    A larger point size yields larger cells; the grid canvas grows to match and
    painting offscreen does not raise.

    Verifies: UIR-069, FR-091a.
    """
    engine = VT100Engine(cols=20, rows=4)
    view = TerminalView(engine, font=QFont("Courier New", 10))
    try:
        w_before, h_before = view._cell_w, view._cell_h
        view.set_font(QFont("Courier New", 24))
        assert view.current_font().pointSize() == 24
        assert view._cell_w > w_before
        assert view._cell_h > h_before
        # The grid canvas tracks the new cell height, and painting still works.
        assert view._grid.height() == view._total_rows() * view._cell_h
        view._grid.grab()  # triggers paintEvent offscreen
    finally:
        view.deleteLater()


def _drag(view, r0, c0, r1, c1):
    """Simulate a left-button click-drag from cell (r0,c0) to (r1,c1)."""
    cw, ch = view._cell_w, view._cell_h
    view._mouse_press(c0 * cw, r0 * ch, Qt.MouseButton.LeftButton)
    view._mouse_move(c1 * cw, r1 * ch)
    view._mouse_release(c1 * cw, r1 * ch, Qt.MouseButton.LeftButton)


def test_mouse_drag_selects_text_on_one_row(qapp):
    """A left click-drag highlights a range whose text is retrievable.

    Verifies: UIR-100, FR-165.
    """
    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine)
    try:
        engine.feed(b"HELLO")
        view.refresh()
        _drag(view, 0, 0, 0, 5)  # cols 0..5 (exclusive) => "HELLO"
        assert view.has_selection()
        assert view.selected_text() == "HELLO"
        view._grid.grab()  # selection paint path must not raise
    finally:
        view.deleteLater()


def test_plain_click_clears_selection(qapp):
    """A left press with no drag clears any existing selection.

    Verifies: UIR-100.
    """
    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine)
    try:
        engine.feed(b"HELLO")
        view.refresh()
        _drag(view, 0, 0, 0, 5)
        assert view.has_selection()
        # Press and release on the same cell (no drag) => cleared.
        cw = view._cell_w
        view._mouse_press(2 * cw, 0, Qt.MouseButton.LeftButton)
        view._mouse_release(2 * cw, 0, Qt.MouseButton.LeftButton)
        assert not view.has_selection()
        assert view.selected_text() == ""
    finally:
        view.deleteLater()


def test_selected_text_trims_trailing_blanks_and_joins_rows(qapp):
    """Multi-row selection trims trailing blanks per row, joins with newline.

    Verifies: FR-165, UIR-100.
    """
    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine)
    try:
        engine.feed(b"AB\r\nCD")  # row0="AB", row1="CD"
        view.refresh()
        # Select from row0 col0 to row1 end: whole first row + "CD".
        _drag(view, 0, 0, 1, engine.cols)
        # Trailing blank cells past "AB"/"CD" are trimmed; rows joined by "\n".
        assert view.selected_text() == "AB\nCD"
    finally:
        view.deleteLater()


def test_copy_selection_puts_text_on_clipboard(qapp):
    """Copy writes the highlighted text to the system clipboard.

    Verifies: FR-165.
    """
    from PySide6.QtWidgets import QApplication as _QApp

    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine)
    try:
        engine.feed(b"COPYME")
        view.refresh()
        _QApp.clipboard().clear()
        _drag(view, 0, 0, 0, 6)
        view.copy_selection()
        assert _QApp.clipboard().text() == "COPYME"
    finally:
        view.deleteLater()


def test_copy_selection_no_selection_is_noop(qapp):
    """Copy with nothing selected leaves the clipboard untouched.

    Verifies: FR-165.
    """
    from PySide6.QtWidgets import QApplication as _QApp

    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine)
    try:
        _QApp.clipboard().setText("previous")
        assert not view.has_selection()
        view.copy_selection()
        assert _QApp.clipboard().text() == "previous"
    finally:
        view.deleteLater()


def test_clear_selection_drops_highlight(qapp):
    """clear_selection removes the current highlight (used on Clear/reset).

    Verifies: UIR-100.
    """
    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine)
    try:
        engine.feed(b"HELLO")
        view.refresh()
        _drag(view, 0, 0, 0, 5)
        assert view.has_selection()
        view.clear_selection()
        assert not view.has_selection()
    finally:
        view.deleteLater()


def test_viewport_size_for_returns_exact_cell_extent(qapp):
    """viewport_size_for gives the pixel size holding cols x rows cells.

    Verifies: FR-167.
    """
    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine)
    try:
        size = view.viewport_size_for(80, 24)
        assert size.width() == 80 * view._cell_w
        assert size.height() == 24 * view._cell_h
    finally:
        view.deleteLater()


def test_context_menu_callback_invoked_with_position(qapp):
    """A right-click reports its global position to the registered handler.

    Verifies: UIR-099.
    """
    from PySide6.QtCore import QPoint

    engine = VT100Engine(cols=10, rows=3)
    view = TerminalView(engine)
    try:
        seen = []
        view.set_context_menu_callback(seen.append)
        view._context_menu(QPoint(5, 7))
        assert seen == [QPoint(5, 7)]
    finally:
        view.deleteLater()
