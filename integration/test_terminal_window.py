"""§12 — Terminal Window over real serial (MT-W*).

Open the Terminal Window, send a line on the Terminal Port, and confirm the live
remote response is rendered into the receive area (FR-091/FR-094/FR-095).
"""

from __future__ import annotations

import pytest
from helpers.trace import get_logger

from cpm_fm.terminal.cpm_parser import CPMParser

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
