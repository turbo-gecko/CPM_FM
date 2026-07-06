"""Tests for the VT-52 / ADM-3A byte-stream translators (term_translate).

These exercise the pure translation from a legacy terminal's control set into
the VT-100/ANSI sequences the shared pyte engine understands, plus the
split-across-chunks reassembly and malformed-input robustness.
"""

from cpm_fm.terminal.term_translate import (
    ADM3A,
    VT52,
    ADM3ATranslator,
    TerminalTranslator,
    VT52Translator,
    make_translator,
)


def _translate(translator, *chunks):
    """Feed each chunk in turn and concatenate the translated output."""
    return b"".join(translator.translate(c) for c in chunks)


# ------------------------------------------------------------------ factory


def test_make_translator_selects_type():
    """Verifies: FR-157, FR-157i, FR-157j, UIR-034."""
    assert isinstance(make_translator(VT52), VT52Translator)
    assert isinstance(make_translator(ADM3A), ADM3ATranslator)


def test_make_translator_defaults_to_identity():
    """Verifies: FR-157, UIR-034."""
    # VT100 and any unknown value fall back to the pass-through translator.
    assert type(make_translator("VT100")) is TerminalTranslator
    assert type(make_translator("bogus")) is TerminalTranslator


def test_identity_translator_passes_through():
    """Verifies: FR-157."""
    t = TerminalTranslator()
    assert t.translate(b"\x1b[2Jhello\r\n") == b"\x1b[2Jhello\r\n"


# --------------------------------------------------------------------- VT-52


def test_vt52_cursor_moves():
    """Verifies: FR-157i."""
    t = VT52Translator()
    assert t.translate(b"\x1bA\x1bB\x1bC\x1bD") == b"\x1b[A\x1b[B\x1b[C\x1b[D"


def test_vt52_home_and_erase():
    """Verifies: FR-157i."""
    t = VT52Translator()
    assert t.translate(b"\x1bH\x1bJ\x1bK") == b"\x1b[H\x1b[J\x1b[K"


def test_vt52_reverse_line_feed():
    """Verifies: FR-157i."""
    assert VT52Translator().translate(b"\x1bI") == b"\x1bM"


def test_vt52_graphics_mode_maps_to_dec_charset():
    """Verifies: FR-157i, FR-157f."""
    t = VT52Translator()
    assert t.translate(b"\x1bF") == b"\x1b(0"
    assert t.translate(b"\x1bG") == b"\x1b(B"


def test_vt52_direct_cursor_address():
    """Verifies: FR-157i."""
    # ESC Y row col; each coordinate is byte-0x20, 0-based. row=0x24 -> 4 -> 5,
    # col=0x29 -> 9 -> 10 (VT-100 CUP is 1-based).
    assert VT52Translator().translate(b"\x1bY\x24\x29") == b"\x1b[5;10H"


def test_vt52_direct_address_split_across_chunks():
    """Verifies: FR-157i."""
    t = VT52Translator()
    # The ESC, the 'Y', and each coordinate byte arrive in separate feeds.
    assert _translate(t, b"\x1b", b"Y", b"\x20", b"\x20") == b"\x1b[1;1H"


def test_vt52_escape_split_across_chunks():
    """Verifies: FR-157i."""
    t = VT52Translator()
    assert _translate(t, b"\x1b", b"A") == b"\x1b[A"


def test_vt52_printables_and_controls_pass_through():
    """Verifies: FR-157i."""
    assert VT52Translator().translate(b"Hi\r\n\t") == b"Hi\r\n\t"


def test_vt52_unknown_and_keypad_sequences_consumed():
    """Verifies: FR-157i, FR-157h."""
    t = VT52Translator()
    # Keypad-mode/identify/ANSI-mode and any unrecognised ESC command are
    # swallowed without emitting anything or desynchronising the stream.
    assert t.translate(b"\x1b=\x1b>\x1bZ\x1b<") == b""
    assert t.translate(b"\x1bQok") == b"ok"


# -------------------------------------------------------------------- ADM-3A


def test_adm3a_cursor_control_codes():
    """Verifies: FR-157j."""
    t = ADM3ATranslator()
    assert t.translate(b"\x0b") == b"\x1b[A"  # Ctrl-K up
    assert t.translate(b"\x0c") == b"\x1b[C"  # Ctrl-L right
    assert t.translate(b"\x1e") == b"\x1b[H"  # RS home


def test_adm3a_clear_screen():
    """Verifies: FR-157j."""
    assert ADM3ATranslator().translate(b"\x1a") == b"\x1b[2J\x1b[H"


def test_adm3a_passthrough_controls():
    """Verifies: FR-157j."""
    # Left (BS), down (LF), and CR are handled by pyte, so they pass through.
    assert ADM3ATranslator().translate(b"A\x08\x0a\x0d") == b"A\x08\x0a\x0d"


def test_adm3a_direct_cursor_address():
    """Verifies: FR-157j."""
    # ESC = row col, 0x20-biased, 0-based.
    assert ADM3ATranslator().translate(b"\x1b=\x24\x29") == b"\x1b[5;10H"


def test_adm3a_direct_address_split_across_chunks():
    """Verifies: FR-157j."""
    t = ADM3ATranslator()
    assert _translate(t, b"\x1b", b"=", b"\x22", b"\x25") == b"\x1b[3;6H"


def test_adm3a_unknown_escape_consumed():
    """Verifies: FR-157j, FR-157h."""
    t = ADM3ATranslator()
    assert t.translate(b"\x1bXok") == b"ok"


def test_translators_never_raise_on_arbitrary_bytes():
    """Verifies: FR-157h, FR-157i, FR-157j."""
    blob = bytes(range(256)) + b"\x1bY\x1b=\x1b"
    # Malformed direct-address bytes (< 0x20) clamp rather than raise.
    for t in (VT52Translator(), ADM3ATranslator()):
        t.translate(blob)  # must not raise
