"""§12 — Terminal Window over real serial (MT-W*).

Open the Terminal Window, send a line on the Terminal Port, and confirm the live
remote response is rendered into the receive area (FR-091/FR-094/FR-095/FR-097).
"""

from __future__ import annotations

import pytest

from cpm_fm.terminal.cpm_parser import CPMParser


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
        lambda: CPMParser.drive_prompt_letter(term.receive_area.toPlainText()) is not None,
        timeout=8.0,
    )
    text = term.receive_area.toPlainText()
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
    term.write_text("SOME OUTPUT")
    assert term.receive_area.toPlainText() != ""
    term.clear_text()
    assert term.receive_area.toPlainText() == ""
