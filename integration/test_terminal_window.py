"""§12 — Terminal Window over real serial (MT-W*).

Open the Terminal Window, send a line on the Terminal Port, and confirm the live
remote response is rendered into the receive area (FR-091/FR-094/FR-095).
"""

from __future__ import annotations

import pytest
from helpers.trace import get_logger

from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.utils.i18n import tr

log = get_logger("terminal-vt100")


def _screen_text(term) -> str:
    """The Terminal Window's rendered screen as plain text.

    The receive area is now a VT-100 grid backed by the engine, so read the
    screen from the engine's display rather than a text widget.
    """
    return "\n".join(term.engine.display)


@pytest.mark.hil
@pytest.mark.mt("MT-W01", "FR-097", "FR-091", "FR-094")
def test_terminal_window_shows_live_response(gui):
    """Sending an EOL in the Terminal Window renders the CP/M drive prompt.

    Verifies: FR-097, FR-091, FR-094.
    """
    assert gui.connect()[0] == "ok"
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    gui.win.handle_terminal_send("")  # bare EOL -> remote echoes its prompt
    gui.process_until(
        lambda: CPMParser.drive_prompt_letter(_screen_text(term)) is not None,
        timeout=8.0,
    )
    text = _screen_text(term)
    assert CPMParser.drive_prompt_letter(text) is not None, f"no prompt rendered: {text!r}"


@pytest.mark.hil
@pytest.mark.mt("MT-W03", "FR-096", "FR-094")
def test_terminal_window_keyboard_input(gui):
    """Typing into the receive area transmits to the port and shows the prompt.

    Exercises the interactive keyboard path (handle_terminal_key) rather than a
    programmatic send: pressing Enter transmits the configured EOL, and the
    remote echoes its drive prompt back onto the screen.

    Verifies: FR-096, FR-094.
    """
    assert gui.connect()[0] == "ok"
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    gui.win.handle_terminal_key(b"\r")  # Enter -> configured EOL on the wire
    gui.process_until(
        lambda: CPMParser.drive_prompt_letter(_screen_text(term)) is not None,
        timeout=8.0,
    )
    text = _screen_text(term)
    assert CPMParser.drive_prompt_letter(text) is not None, f"no prompt rendered: {text!r}"


@pytest.mark.hil
@pytest.mark.mt("MT-W05", "FR-095")
def test_terminal_window_clear(gui):
    """The Terminal Window Clear empties the receive area.

    Verifies: FR-095.
    """
    assert gui.connect()[0] == "ok"
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    term.engine.feed(b"SOME OUTPUT")
    term.render_screen()
    assert _screen_text(term).strip() != ""
    term.clear_text()
    assert _screen_text(term).strip() == ""


@pytest.mark.hil
@pytest.mark.mt("MT-W14", "FR-162", "FR-164", "UIR-096", "UIR-097")
def test_macro_button_sends_keystrokes_over_serial(gui):
    """A configured macro button transmits its script and the remote responds.

    Configure one macro slot to send a carriage return (SENDRAW 0D), open the
    Terminal Window, reveal the Macro Window via the Macros checkbox, and click
    the generated button. The keystroke script runs on the Terminal Port and the
    remote echoes its drive prompt onto the screen.

    Verifies: FR-162, FR-164, UIR-096, UIR-097.
    """
    from PySide6.QtWidgets import QPushButton

    assert gui.connect()[0] == "ok"
    # FR-162: one macro slot that sends a bare CR to elicit the drive prompt.
    gui.win.settings["macro_1_label"] = "Prompt"
    gui.win.settings["macro_1_seq"] = "SENDRAW 0D"

    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    # UIR-096/FR-164: the Macros checkbox shows the palette.
    term.chk_macros.setChecked(True)
    assert gui.win.macro_win is not None, "macro window was not created"
    buttons = gui.win.macro_win.centralWidget().findChildren(QPushButton)
    assert [b.text() for b in buttons] == ["Prompt"], "configured macro button not shown"

    buttons[0].click()  # FR-162: runs the script on the Terminal Port
    gui.process_until(
        lambda: CPMParser.drive_prompt_letter(_screen_text(term)) is not None,
        timeout=8.0,
    )
    text = _screen_text(term)
    assert CPMParser.drive_prompt_letter(text) is not None, f"no prompt rendered: {text!r}"


@pytest.mark.hil
@pytest.mark.mt("MT-W17", "UIR-099", "UIR-100", "FR-165")
def test_terminal_context_menu_copy_selection(gui):
    """The Receive-view context menu offers five items; Copy copies a selection.

    Feed known text onto the screen, drag-select it, and confirm the context
    menu's Copy action places the highlighted text on the system clipboard.

    Verifies: UIR-099, UIR-100, FR-165.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    assert gui.connect()[0] == "ok"
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    # UIR-099: five top-level command actions (excluding separators and the
    # Terminal Type / Macros submenus, UIR-101/UIR-102).
    menu = term._build_context_menu()
    labels = [a.text() for a in menu.actions() if not a.isSeparator() and a.menu() is None]
    assert len(labels) == 5, f"expected 5 menu items, got {labels}"

    # Clear first so the screen layout is deterministic — a live connection has
    # already rendered the drive prompt / listing, leaving the cursor mid-screen.
    # No events are processed between here and the copy, so no remote bytes can
    # interleave and shift what row 0 holds.
    term.clear_text()
    term.engine.feed(b"COPYTEST")
    term.render_screen()
    view = term.receive_area
    cw = view._cell_w
    # UIR-100: drag-select the eight characters on row 0.
    view._mouse_press(0, 0, Qt.MouseButton.LeftButton)
    view._mouse_move(8 * cw, 0)
    view._mouse_release(8 * cw, 0, Qt.MouseButton.LeftButton)
    assert view.has_selection()

    QApplication.clipboard().clear()
    view.copy_selection()  # FR-165
    assert QApplication.clipboard().text() == "COPYTEST"


@pytest.mark.hil
@pytest.mark.mt("MT-W17", "FR-166", "FR-094")
def test_terminal_context_menu_paste_sends_over_serial(gui):
    """The context-menu Paste transmits the clipboard text on the Terminal Port.

    Put a carriage return on the clipboard and invoke Paste; the EOL goes out on
    the wire and the remote echoes its drive prompt onto the screen.

    Verifies: FR-166, FR-094.
    """
    from PySide6.QtWidgets import QApplication

    assert gui.connect()[0] == "ok"
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    QApplication.clipboard().setText("\n")  # normalises to the configured EOL
    term._on_paste()  # FR-166: send the clipboard text on the Terminal Port
    gui.process_until(
        lambda: CPMParser.drive_prompt_letter(_screen_text(term)) is not None,
        timeout=8.0,
    )
    text = _screen_text(term)
    assert CPMParser.drive_prompt_letter(text) is not None, f"no prompt rendered: {text!r}"


@pytest.mark.hil
@pytest.mark.mt("MT-W18", "FR-167", "FR-091a")
def test_terminal_context_menu_reset_size(gui):
    """The context-menu Reset Size reflows the grid to 80 columns x 24 rows.

    Verifies: FR-167, FR-091a.
    """
    assert gui.connect()[0] == "ok"
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    term.resize(320, 220)  # some off-target size first
    gui.process_until(lambda: True, timeout=0.5)
    term.reset_size()  # FR-167
    gui.process_until(
        lambda: (term.engine.cols, term.engine.rows) == (80, 24),
        timeout=4.0,
    )
    assert (term.engine.cols, term.engine.rows) == (80, 24)


@pytest.mark.hil
@pytest.mark.mt("MT-W19", "UIR-101", "UIR-034")
def test_terminal_context_menu_terminal_type_submenu(gui):
    """The Terminal Type submenu switches the running terminal's emulation.

    The submenu lists the three types with the active one checked; choosing a
    different type applies it to the engine and updates the setting.

    Verifies: UIR-101, UIR-034.
    """
    from cpm_fm.terminal.term_translate import ADM3A, TERMINAL_TYPES

    assert gui.connect()[0] == "ok"
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    menu = term._build_context_menu()  # held so the submenu is not GC'd
    sub = {a.menu().title(): a.menu() for a in menu.actions() if a.menu() is not None}[
        tr("terminal.menu.terminal_type")
    ]
    labels = [a.text() for a in sub.actions()]
    assert labels == list(TERMINAL_TYPES), f"unexpected type list: {labels}"

    next(a for a in sub.actions() if a.text() == ADM3A).trigger()
    assert term.engine.terminal_type == ADM3A
    assert gui.win.settings["terminal_type"] == ADM3A


@pytest.mark.hil
@pytest.mark.mt("MT-W20", "UIR-102", "FR-162")
def test_terminal_context_menu_macros_submenu_runs_over_serial(gui):
    """The Macros submenu runs a configured macro's script on the Terminal Port.

    Configure one macro slot to send a carriage return, then trigger it from the
    context menu's Macros submenu; the remote echoes its drive prompt.

    Verifies: UIR-102, FR-162.
    """
    assert gui.connect()[0] == "ok"
    gui.win.settings["macro_1_label"] = "Prompt"
    gui.win.settings["macro_1_seq"] = "SENDRAW 0D"

    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    menu = term._build_context_menu()  # held so the submenu is not GC'd
    sub = {a.menu().title(): a.menu() for a in menu.actions() if a.menu() is not None}[
        tr("terminal.menu.macros_sub")
    ]
    assert [a.text() for a in sub.actions()] == ["Prompt"], "configured macro not listed"

    sub.actions()[0].trigger()  # FR-162: runs the script on the Terminal Port
    gui.process_until(
        lambda: CPMParser.drive_prompt_letter(_screen_text(term)) is not None,
        timeout=8.0,
    )
    text = _screen_text(term)
    assert CPMParser.drive_prompt_letter(text) is not None, f"no prompt rendered: {text!r}"


@pytest.mark.hil
@pytest.mark.mt("MT-W10", "FR-157")
def test_terminal_vt100_escape_sequences_render_without_crash(gui):
    """VT-100 escape sequences (cursor move, clear, SGR attributes) render without crash.

    Verifies: FR-157.
    """
    assert gui.connect()[0] == "ok"
    gui.win.show_terminal()
    term = gui.win.terminal_win
    assert term is not None, "terminal window was not created"

    # Cursor positioning (CUP): ESC[5;10H → row 5, col 10
    term.engine.feed(b"\x1b[5;10H")
    # Erase in line (EL): ESC[K → clear to end of line
    term.engine.feed(b"\x1b[K")
    # Erase in display (ED): ESC[J → clear to end of screen
    term.engine.feed(b"\x1b[J")
    # SGR bold: ESC[1m
    term.engine.feed(b"\x1b[1m")
    # SGR reset: ESC[0m
    term.engine.feed(b"\x1b[0m")
    # Some printable text after escapes
    term.engine.feed(b"ESCAPES OK")

    term.render_screen()
    text = _screen_text(term)
    # The engine should have processed all sequences without raising
    assert text is not None
    rows = len(term.engine.display)
    cols = len(term.engine.display[0]) if term.engine.display else 0
    log.info("VT-100 escapes OK (screen %dx%d)", rows, cols)
