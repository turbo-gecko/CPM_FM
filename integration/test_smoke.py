"""Phase 0 connectivity smoke test.

Opens the configured terminal port for the selected target, sends a bare EOL,
and confirms a CP/M drive prompt comes back — proving the bench wiring, the
settings file, and the read path before any of the heavier protocol/GUI tiers
run. Self-contained on ``SerialManager`` + ``CPMParser`` (no GUI, CR-014).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from helpers.config import EOL_MAP
from helpers.trace import get_logger

from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.terminal.serial_manager import SerialManager

log = get_logger("smoke")


@pytest.mark.hil
@pytest.mark.mt("MT-SMOKE", "FR-041", "FR-042")
def test_peer_connects_and_sees_ccp_prompt(target, settings_copy):
    """Verifies the bench is reachable: a bare EOL yields a CP/M drive prompt.

    Verifies: FR-041, FR-042.
    """
    settings = json.loads(Path(settings_copy).read_text())
    port = settings.get("terminal_port")
    sm = SerialManager()
    # SerialManager delivers raw bytes (v2.17); decode with the app's ASCII/
    # replace rule for prompt parsing.
    chunks: list[bytes] = []
    sm.on_data_received = chunks.append

    assert sm.open_port("terminal", settings), f"could not open terminal port {port!r}"
    try:
        eol = EOL_MAP.get(str(settings.get("eol", "CR")), "\r")
        letter = None
        received = ""
        for _ in range(3):
            chunks.clear()
            sm.send_data("terminal", eol)
            time.sleep(1.5)
            received = b"".join(chunks).decode("ascii", errors="replace")
            letter = CPMParser.drive_prompt_letter(received)
            if letter:
                break
        assert letter is not None, f"no CP/M drive prompt on {port}; received: {received!r}"
        log.info("target=%s port=%s CCP drive prompt = %s:", target.name, port, letter)
    finally:
        sm.close_ports()
