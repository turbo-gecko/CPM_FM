"""§5 — GUI connect/disconnect over real serial (MT-C*).

Drives the real ``MainWindow`` against the live peer: Connect opens both ports,
the post-connect probe finds the drive and populates the Remote Files list;
Disconnect closes the ports and clears the list. The three-button "remote
unavailable" dialog (FR-044) and the forced-close failure (MT-C10) need an
unresponsive/uncloseable peer that a healthy bench rig can't produce on demand;
those stay covered by the unit suite (``tests/test_gui_smoke.py``) and manual
testing, and are noted in the README.
"""

from __future__ import annotations

import pytest


@pytest.mark.hil
@pytest.mark.mt("MT-C01", "FR-030", "FR-037", "FR-041", "FR-042")
def test_connect_opens_ports_and_probes(gui):
    """Connect opens both ports and the probe returns a drive prompt.

    Verifies: FR-030, FR-037, FR-041, FR-042.
    """
    result = gui.connect()
    assert gui.connected, "terminal port did not open"
    assert gui.transport_connected, "transport flag not set after connect"
    assert result is not None and result[0] == "ok", f"probe did not succeed: {result}"
    drive = result[1]
    assert drive and gui.win.drive_combo.currentText() == f"{drive}:"
    print(
        f"[gui-connect] connected; remote drive {drive}: ({len(gui.remote_names())} file(s) listed)"
    )


@pytest.mark.hil
@pytest.mark.mt("MT-C05", "FR-050", "FR-055", "FR-058")
def test_disconnect_closes_ports_and_clears_list(gui):
    """Disconnect drops both status flags and clears the Remote Files list.

    Verifies: FR-050, FR-055, FR-058.
    """
    assert gui.connect()[0] == "ok"
    gui.win.remote_list.addItem("STALE.TXT")  # ensure there is something to clear
    gui.disconnect()
    assert not gui.connected
    assert not gui.transport_connected
    assert gui.remote_names() == []


@pytest.mark.hil
@pytest.mark.mt("MT-C06", "FR-030", "FR-050")
def test_reconnect_after_disconnect(gui):
    """The port can be reopened after a clean disconnect (no leaked handle).

    Verifies: FR-030, FR-050.
    """
    assert gui.connect()[0] == "ok"
    gui.disconnect()
    assert not gui.connected
    assert gui.connect()[0] == "ok"
    assert gui.connected and gui.transport_connected
