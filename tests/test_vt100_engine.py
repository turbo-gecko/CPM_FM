from cpm_fm.terminal.vt100_engine import DEFAULT_COLS, DEFAULT_ROWS, VT100Engine


def _text(engine, row):
    """Row ``row`` as a right-stripped string."""
    return engine.display[row].rstrip()


def test_default_geometry():
    """Verifies: FR-091."""
    e = VT100Engine()
    assert (e.cols, e.rows) == (DEFAULT_COLS, DEFAULT_ROWS)
    assert e.cursor == (0, 0)


def test_plain_text_and_cursor_advance():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.feed(b"Hello")
    assert _text(e, 0) == "Hello"
    assert e.cursor == (5, 0)


def test_crlf_moves_to_next_line():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.feed(b"line1\r\nline2")
    assert _text(e, 0) == "line1"
    assert _text(e, 1) == "line2"
    assert e.cursor == (5, 1)


def test_backspace_moves_cursor_left():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.feed(b"abc\x08\x08X")
    # Backspace is non-destructive cursor movement; the overwrite replaces 'b'.
    assert _text(e, 0) == "aXc"


def test_tab_advances_to_next_tab_stop():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.feed(b"a\tb")
    # Default tab stops every 8 columns: 'a' at col 0, tab -> col 8, 'b' at col 8.
    assert e.cursor == (9, 0)
    assert e.display[0][8] == "b"


def test_cursor_addressing_cup():
    """Verifies: FR-091, FR-157."""
    e = VT100Engine()
    # ESC[5;10H -> row 5, col 10 (1-based) => zero-based (9, 4).
    e.feed(b"\x1b[5;10Habc")
    assert e.cursor == (12, 4)
    assert _text(e, 4) == "         abc"


def test_cursor_relative_moves():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.feed(b"\x1b[10;10H")  # to (9, 9)
    e.feed(b"\x1b[2A")  # up 2
    e.feed(b"\x1b[3C")  # right 3
    assert e.cursor == (12, 7)


def test_erase_in_display_clears_screen():
    """Verifies: FR-091, FR-157."""
    e = VT100Engine()
    e.feed(b"line1\r\nline2\r\n")
    e.feed(b"\x1b[H\x1b[J")  # home, then erase to end of display
    assert _text(e, 0) == ""
    assert _text(e, 1) == ""


def test_erase_in_line_clears_to_end():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.feed(b"abcdef")
    e.feed(b"\x1b[1;4H")  # cursor to col 4 (zero-based 3)
    e.feed(b"\x1b[K")  # erase from cursor to end of line
    assert _text(e, 0) == "abc"


def test_sgr_bold_reverse_and_reset():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.feed(b"\x1b[1;7mX\x1b[0mY")
    row = e.line(0)
    assert row[0].char == "X" and row[0].bold and row[0].reverse
    assert row[1].char == "Y" and not row[1].bold and not row[1].reverse


def test_sgr_ansi_colours():
    """Verifies: FR-091, FR-157."""
    e = VT100Engine()
    e.feed(b"\x1b[31;42mZ\x1b[0m")
    cell = e.line(0)[0]
    assert cell.char == "Z"
    assert cell.fg == "red"
    assert cell.bg == "green"


def test_line_returns_full_width_padded():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.feed(b"hi")
    row = e.line(0)
    assert len(row) == e.cols
    assert row[0].char == "h"
    # Unwritten cells are blank defaults.
    assert row[5].char == " "
    assert row[5].fg == "default"


def test_cursor_hidden_toggle():
    """Verifies: FR-091."""
    e = VT100Engine()
    assert e.cursor_hidden is False
    e.feed(b"\x1b[?25l")
    assert e.cursor_hidden is True
    e.feed(b"\x1b[?25h")
    assert e.cursor_hidden is False


def test_escape_sequence_split_across_feeds():
    """A CSI split across two feed() calls is reassembled, not shown literally.

    Verifies: FR-091, FR-157, NFR-001.
    """
    e = VT100Engine()
    e.feed(b"\x1b[5")  # partial CSI: parameter interrupted mid-sequence
    e.feed(b";10Hok")  # remainder arrives in the next chunk
    assert e.cursor == (11, 4)
    assert _text(e, 4) == "         ok"


def test_utf8_multibyte_split_across_feeds():
    """A UTF-8 code point split across feed() boundaries decodes correctly.

    Verifies: FR-091, NFR-001.
    """
    e = VT100Engine()
    star = "★".encode()  # ★, three bytes (UTF-8)
    e.feed(star[:1])
    e.feed(star[1:])
    assert _text(e, 0) == "★"


def test_raw_8bit_mode_maps_bytes_directly():
    """Verifies: FR-091."""
    e = VT100Engine(use_utf8=False)
    # 0xC9 is 'É' in Latin-1; with UTF-8 off each byte maps to its code point.
    e.feed(b"\xc9")
    assert _text(e, 0) == "É"


def test_reset_clears_screen_and_cursor():
    """Verifies: FR-091, FR-095."""
    e = VT100Engine()
    e.feed(b"some text\r\nmore")
    e.reset()
    assert _text(e, 0) == ""
    assert _text(e, 1) == ""
    assert e.cursor == (0, 0)


def test_reset_marks_all_lines_dirty():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.clear_dirty()
    e.reset()
    assert e.dirty == set(range(e.rows))


def test_dirty_tracking_and_clear():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.clear_dirty()
    assert e.dirty == set()
    e.feed(b"x")
    assert 0 in e.dirty
    e.clear_dirty()
    assert e.dirty == set()


def test_resize_changes_geometry():
    """Verifies: FR-091."""
    e = VT100Engine()
    e.resize(40, 12)
    assert (e.cols, e.rows) == (40, 12)


def test_engine_imports_no_gui_toolkit():
    """The engine must not pull in any GUI toolkit (layer boundary).

    Run in a fresh subprocess so the result is independent of whatever the rest
    of the suite (e.g. the GUI smoke tests) has already imported.

    Verifies: CR-014.
    """
    import subprocess
    import sys

    code = (
        "import sys; import cpm_fm.terminal.vt100_engine as m; "
        "m.VT100Engine().feed(b'hi'); "
        "gui={'PySide6','PyQt5','PyQt6','tkinter','wx'}; "
        "loaded={n.split('.')[0] for n in sys.modules}; "
        "bad=gui & loaded; "
        "print(sorted(bad)); "
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, f"GUI toolkit imported by engine: {result.stdout.strip()}"
