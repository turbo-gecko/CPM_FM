"""Unit tests for the pure boot-sequence script parser (cpm_fm.terminal.boot_sequence).

These exercise the GUI-free parser without a running Qt application (CR-014):
directive recognition, comment/blank-line handling, hex parsing for SENDRAW,
the WAITFOR timeout heuristic, and malformed-input rejection.

Satisfies: FR-047.
"""

from __future__ import annotations

import pytest

from cpm_fm.terminal.boot_sequence import (
    DEFAULT_WAITFOR_TIMEOUT,
    SEND,
    SENDRAW,
    WAIT,
    WAITFOR,
    parse_boot_sequence,
)


def test_empty_script_yields_no_steps():
    """Verifies: FR-047."""
    assert parse_boot_sequence("") == []
    assert parse_boot_sequence("   \n\t\n") == []


def test_comments_and_blank_lines_ignored():
    """Verifies: FR-047."""
    script = "# a comment\n\n   # indented comment\nSEND HELLO\n"
    steps = parse_boot_sequence(script)
    assert len(steps) == 1
    assert steps[0].kind == SEND
    assert steps[0].text == "HELLO"


def test_send_preserves_argument_text():
    """Verifies: FR-047."""
    # The text after the keyword is kept (internal spaces preserved).
    steps = parse_boot_sequence("SEND A:RUN CPM")
    assert steps[0].kind == SEND
    assert steps[0].text == "A:RUN CPM"


def test_send_with_empty_text_is_a_bare_eol():
    """Verifies: FR-047."""
    # A bare SEND transmits just the configured EOL (empty text).
    steps = parse_boot_sequence("SEND")
    assert steps[0].kind == SEND
    assert steps[0].text == ""


def test_keyword_is_case_insensitive():
    """Verifies: FR-047."""
    steps = parse_boot_sequence("send hi\nWaIt 1\nSendRaw 03")
    assert [s.kind for s in steps] == [SEND, WAIT, SENDRAW]


def test_sendraw_parses_hex_bytes():
    """Verifies: FR-047."""
    steps = parse_boot_sequence("SENDRAW 03 1B 0D")
    assert steps[0].kind == SENDRAW
    assert steps[0].data == bytes([0x03, 0x1B, 0x0D])


def test_sendraw_rejects_invalid_hex():
    """Verifies: FR-047."""
    with pytest.raises(ValueError):
        parse_boot_sequence("SENDRAW ZZ")


def test_sendraw_rejects_out_of_range_byte():
    """Verifies: FR-047."""
    with pytest.raises(ValueError):
        parse_boot_sequence("SENDRAW 1FF")


def test_sendraw_requires_at_least_one_byte():
    """Verifies: FR-047."""
    with pytest.raises(ValueError):
        parse_boot_sequence("SENDRAW")


def test_wait_parses_decimal_seconds():
    """Verifies: FR-047."""
    steps = parse_boot_sequence("WAIT 2.5")
    assert steps[0].kind == WAIT
    assert steps[0].seconds == pytest.approx(2.5)


def test_wait_rejects_non_numeric_and_negative():
    """Verifies: FR-047."""
    with pytest.raises(ValueError):
        parse_boot_sequence("WAIT soon")
    with pytest.raises(ValueError):
        parse_boot_sequence("WAIT -1")


def test_waitfor_without_timeout_uses_default():
    """Verifies: FR-047."""
    steps = parse_boot_sequence("WAITFOR Boot:")
    assert steps[0].kind == WAITFOR
    assert steps[0].text == "Boot:"
    assert steps[0].seconds == pytest.approx(DEFAULT_WAITFOR_TIMEOUT)


def test_waitfor_with_trailing_timeout():
    """Verifies: FR-047."""
    steps = parse_boot_sequence("WAITFOR Boot: 5")
    assert steps[0].text == "Boot:"
    assert steps[0].seconds == pytest.approx(5.0)


def test_waitfor_target_may_contain_spaces_when_no_timeout():
    """Verifies: FR-047."""
    # The trailing token is not numeric, so the whole argument is the target.
    steps = parse_boot_sequence("WAITFOR Press any key")
    assert steps[0].text == "Press any key"
    assert steps[0].seconds == pytest.approx(DEFAULT_WAITFOR_TIMEOUT)


def test_waitfor_requires_target():
    """Verifies: FR-047."""
    with pytest.raises(ValueError):
        parse_boot_sequence("WAITFOR")


def test_unknown_directive_rejected():
    """Verifies: FR-047."""
    with pytest.raises(ValueError):
        parse_boot_sequence("REBOOT now")


def test_full_sequence_order_preserved():
    """Verifies: FR-047."""
    script = "WAITFOR Boot: 3\nSENDRAW 0D\nWAIT 1\nSEND DDT\n"
    steps = parse_boot_sequence(script)
    assert [s.kind for s in steps] == [WAITFOR, SENDRAW, WAIT, SEND]
