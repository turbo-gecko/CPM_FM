"""Boot-sequence script parsing for the configurable boot-into-CP/M feature.

Pure, GUI-free parsing of the ``boot_sequence`` setting (UIR-059) into an
ordered list of :class:`BootStep` directives that the GUI layer
(``gui/mw_remote.py:run_boot_sequence``) executes against the Terminal Port.
Kept in the ``terminal/`` layer so it has no GUI-toolkit imports (CR-014) and is
unit-testable without a running Qt app.

Satisfies: FR-047.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Directive kinds (the ``kind`` field of a BootStep).
SEND = "send"
SENDRAW = "sendraw"
WAIT = "wait"
WAITFOR = "waitfor"

# Default WAITFOR timeout (seconds) when the directive omits one (FR-047).
DEFAULT_WAITFOR_TIMEOUT = 10.0


@dataclass
class BootStep:
    """One parsed boot-sequence directive.

    ``kind`` selects which fields are meaningful: ``SEND``/``WAITFOR`` use
    ``text``; ``SENDRAW`` uses ``data``; ``WAIT`` uses ``seconds``; ``WAITFOR``
    also uses ``seconds`` as its timeout.

    Satisfies: FR-047.
    """

    kind: str
    text: str = ""
    data: bytes = field(default=b"")
    seconds: float = 0.0


def _parse_hex_bytes(rest: str) -> bytes:
    """Parse a SENDRAW argument (space-separated two-digit hex) into bytes.

    Satisfies: FR-047.
    """
    out = bytearray()
    for token in rest.split():
        try:
            value = int(token, 16)
        except ValueError as exc:
            raise ValueError(f"invalid hex byte '{token}' in SENDRAW") from exc
        if not 0 <= value <= 0xFF:
            raise ValueError(f"hex byte '{token}' out of range in SENDRAW")
        out.append(value)
    if not out:
        raise ValueError("SENDRAW requires at least one hex byte")
    return bytes(out)


def _parse_waitfor(rest: str) -> BootStep:
    """Parse a WAITFOR argument: ``<text> [seconds]``.

    The optional trailing timeout is recognised only when the last
    whitespace-separated token parses as a number; otherwise the whole argument
    is the target text and the default timeout applies. This lets the target
    text itself contain spaces.

    Satisfies: FR-047.
    """
    if not rest:
        raise ValueError("WAITFOR requires target text")
    tokens = rest.rsplit(None, 1)
    if len(tokens) == 2:
        try:
            timeout = float(tokens[1])
        except ValueError:
            return BootStep(WAITFOR, text=rest, seconds=DEFAULT_WAITFOR_TIMEOUT)
        return BootStep(WAITFOR, text=tokens[0], seconds=timeout)
    return BootStep(WAITFOR, text=rest, seconds=DEFAULT_WAITFOR_TIMEOUT)


def parse_boot_sequence(text: str) -> list[BootStep]:
    """Parse a boot-sequence script into an ordered list of :class:`BootStep`.

    One directive per line; blank lines and lines whose first non-whitespace
    character is ``#`` are ignored. The directive keyword is case-insensitive.
    Supported directives (FR-047): ``SEND <text>``, ``SENDRAW <hh> [hh ...]``,
    ``WAIT <seconds>``, ``WAITFOR <text> [seconds]``.

    Raises :class:`ValueError` on a malformed line so the caller can surface the
    error rather than silently mis-booting.

    Satisfies: FR-047.
    """
    steps: list[BootStep] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        keyword = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ""

        if keyword == "SEND":
            steps.append(BootStep(SEND, text=rest))
        elif keyword == "SENDRAW":
            steps.append(BootStep(SENDRAW, data=_parse_hex_bytes(rest)))
        elif keyword == "WAIT":
            try:
                seconds = float(rest)
            except ValueError as exc:
                raise ValueError(f"WAIT requires a number of seconds, got '{rest}'") from exc
            if seconds < 0:
                raise ValueError("WAIT seconds must not be negative")
            steps.append(BootStep(WAIT, seconds=seconds))
        elif keyword == "WAITFOR":
            steps.append(_parse_waitfor(rest))
        else:
            raise ValueError(f"unknown boot-sequence directive '{parts[0]}'")
    return steps
