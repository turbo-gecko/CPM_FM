from __future__ import annotations

# Terminal-type byte-stream translators.
#
# The interactive terminal renders everything through a single pyte-backed
# VT-100 screen model (vt100_engine.py). To support the legacy CP/M terminal
# types selected by `terminal_type` (UIR-034) without a second renderer, each
# non-VT-100 type is handled by a stateful translator that rewrites its
# control/escape sequences into the equivalent VT-100/ANSI sequences *before*
# they reach pyte. VT-100/ANSI itself needs no translation (identity).
#
# Translators are GUI-free and live in terminal/ alongside the engine (CR-014),
# and are driven purely from unit tests. They are stateful across translate()
# calls so an escape sequence split across two serial chunks is reassembled,
# mirroring how pyte's own Stream buffers partial sequences (NFR-001).

# terminal_type setting values (UIR-034). ADM-3A keeps its hyphen so the value
# reads naturally in the config file and the Serial Config dropdown.
VT100 = "VT100"
VT52 = "VT52"
ADM3A = "ADM-3A"
TERMINAL_TYPES = (VT100, VT52, ADM3A)

_ESC = 0x1B


def _cup(row_byte: int, col_byte: int) -> bytes:
    """VT-100 CUP for a VT-52/ADM-3A direct-address pair (0x20-biased, 0-based).

    Both terminal types encode a cursor address as two bytes each offset by
    0x20 (space) from a 0-based coordinate. VT-100 CUP is 1-based, so the
    result is ``ESC[<row+1>;<col+1>H``. Bytes below 0x20 (malformed) clamp to
    coordinate 0 rather than raising (FR-157h robustness).

    Satisfies: FR-157i, FR-157j, FR-157h.
    """
    row = max(0, row_byte - 0x20) + 1
    col = max(0, col_byte - 0x20) + 1
    return f"\x1b[{row};{col}H".encode("latin-1")


class TerminalTranslator:
    """Identity translator: VT-100/ANSI bytes pass straight through to pyte.

    The base class is used directly for the VT-100 terminal type and is the
    fallback for any unrecognised `terminal_type` value.

    Satisfies: FR-157.
    """

    def translate(self, data: bytes) -> bytes:
        """Return the VT-100/ANSI byte stream to feed pyte (here, unchanged).

        Satisfies: FR-157.
        """
        return data

    def reset(self) -> None:
        """Discard any partial-sequence state. No-op for the identity case.

        Satisfies: FR-157.
        """


# VT-52 single-character escape commands that map to a fixed VT-100 sequence.
_VT52_SIMPLE: dict[int, bytes] = {
    ord("A"): b"\x1b[A",  # cursor up
    ord("B"): b"\x1b[B",  # cursor down
    ord("C"): b"\x1b[C",  # cursor right
    ord("D"): b"\x1b[D",  # cursor left
    ord("H"): b"\x1b[H",  # cursor home
    ord("I"): b"\x1bM",  # reverse line feed (RI)
    ord("J"): b"\x1b[J",  # erase to end of screen
    ord("K"): b"\x1b[K",  # erase to end of line
    ord("F"): b"\x1b(0",  # enter graphics mode -> DEC line drawing
    ord("G"): b"\x1b(B",  # exit graphics mode -> ASCII
}

# States for the two-byte direct-address collectors.
_GROUND = 0
_ESCAPE = 1
_NEED_ROW = 2
_NEED_COL = 3


class VT52Translator(TerminalTranslator):
    """Translate a VT-52 byte stream into VT-100/ANSI for the shared engine.

    Satisfies: FR-157i.
    """

    def __init__(self) -> None:
        """Satisfies: FR-157i."""
        self._state = _GROUND
        self._row = 0

    def reset(self) -> None:
        """Return to the ground state, discarding any partial escape sequence.

        Satisfies: FR-157i.
        """
        self._state = _GROUND
        self._row = 0

    def translate(self, data: bytes) -> bytes:
        """Rewrite VT-52 sequences in ``data`` to their VT-100 equivalents.

        Satisfies: FR-157i, FR-157h.
        """
        out = bytearray()
        for b in data:
            if self._state == _GROUND:
                if b == _ESC:
                    self._state = _ESCAPE
                else:
                    out.append(b)
            elif self._state == _ESCAPE:
                if b == ord("Y"):
                    self._state = _NEED_ROW
                elif b == _ESC:
                    # A fresh ESC restarts the escape; the prior one had no
                    # command byte.
                    self._state = _ESCAPE
                else:
                    # Fixed command, keypad/identify/ANSI-mode no-op, or unknown:
                    # emit the mapping if any, then return to ground.
                    out += _VT52_SIMPLE.get(b, b"")
                    self._state = _GROUND
            elif self._state == _NEED_ROW:
                self._row = b
                self._state = _NEED_COL
            else:  # _NEED_COL
                out += _cup(self._row, b)
                self._state = _GROUND
        return bytes(out)


# ADM-3A control bytes (in the ground state) that map to a VT-100 sequence.
# Bytes not listed here (BS/LF/CR/BEL/Tab and printables) pass through, so pyte
# applies its own C0 handling to them.
_ADM3A_CTRL: dict[int, bytes] = {
    0x0B: b"\x1b[A",  # Ctrl-K -> cursor up
    0x0C: b"\x1b[C",  # Ctrl-L -> cursor right
    0x1E: b"\x1b[H",  # Ctrl-^ (RS) -> cursor home
    0x1A: b"\x1b[2J\x1b[H",  # Ctrl-Z -> clear screen and home
}


class ADM3ATranslator(TerminalTranslator):
    """Translate a Lear Siegler ADM-3A byte stream into VT-100/ANSI.

    Satisfies: FR-157j.
    """

    def __init__(self) -> None:
        """Satisfies: FR-157j."""
        self._state = _GROUND
        self._row = 0

    def reset(self) -> None:
        """Return to the ground state, discarding any partial escape sequence.

        Satisfies: FR-157j.
        """
        self._state = _GROUND
        self._row = 0

    def translate(self, data: bytes) -> bytes:
        """Rewrite ADM-3A sequences in ``data`` to their VT-100 equivalents.

        Satisfies: FR-157j, FR-157h.
        """
        out = bytearray()
        for b in data:
            if self._state == _GROUND:
                if b == _ESC:
                    self._state = _ESCAPE
                else:
                    out += _ADM3A_CTRL.get(b, bytes([b]))
            elif self._state == _ESCAPE:
                if b == ord("="):
                    self._state = _NEED_ROW
                elif b == _ESC:
                    self._state = _ESCAPE
                else:
                    # ADM-3A has no other escape sequences we render; consume.
                    self._state = _GROUND
            elif self._state == _NEED_ROW:
                self._row = b
                self._state = _NEED_COL
            else:  # _NEED_COL
                out += _cup(self._row, b)
                self._state = _GROUND
        return bytes(out)


def make_translator(terminal_type: str) -> TerminalTranslator:
    """Return a fresh translator for ``terminal_type`` (UIR-034).

    Any unrecognised value falls back to the identity (VT-100) translator so a
    stale or hand-edited config never breaks the terminal.

    Satisfies: FR-157, FR-157i, FR-157j, UIR-034.
    """
    if terminal_type == VT52:
        return VT52Translator()
    if terminal_type == ADM3A:
        return ADM3ATranslator()
    return TerminalTranslator()
