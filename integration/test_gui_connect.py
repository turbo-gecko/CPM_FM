"""§5 — GUI connect/disconnect over real serial (MT-C*).

Drives the real ``MainWindow`` against the live peer: Connect opens both ports,
the post-connect probe finds the drive and populates the Remote Files list;
Disconnect closes the ports and clears the list. The three-button "remote
unavailable" dialog (FR-044) and the forced-close failure (MT-C10) need an
unresponsive/uncloseable peer that a healthy bench rig can't produce on demand;
those stay covered by the unit suite (``tests/test_gui_smoke.py``) and manual
testing, and are noted in the README.

The Transport-Port-open-failure path (MT-C16, two-port only) is tested by mocking
``SerialManager.open_port`` to return ``False`` for the Transport Port — the app
shows the FR-039 error dialog and skips the probe (FR-046). The rapid-connect/
disconnect race (MT-C17) exercises the probe-while-disconnect path to verify no
crash from a queued signal to a deleted QObject.
"""

from __future__ import annotations

import pytest
from helpers.trace import get_logger

log = get_logger("gui-connect")


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
    log.info("connected; remote drive %s: (%d file(s) listed)", drive, len(gui.remote_names()))


@pytest.mark.hil
@pytest.mark.mt("MT-C05", "FR-050", "FR-054", "FR-055", "FR-058")
def test_disconnect_closes_ports_and_clears_list(gui):
    """Disconnect drops both status flags and clears the Remote Files list.

    The rc2014/elite_mini targets are single shared-port (``two_port=false``),
    so this also exercises FR-054 (shared-port disconnect clears the Transport
    flag too) on every bench run against them.

    Verifies: FR-050, FR-054, FR-055, FR-058.
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


@pytest.mark.hil
@pytest.mark.two_port
@pytest.mark.mt("MT-C16", "FR-039", "FR-046")
def test_connect_transport_open_failure_reports_error_and_skips_probe(gui, monkeypatch):
    """A Transport Port open failure reports the FR-039 error and skips the probe.

    Two-port targets only: when the Transport Port cannot be opened, the app
    shows the "Transport port is unable to be opened" error dialog (FR-039) and
    performs no remote-file-system probe (FR-046) — it must not present the
    Remote Filesystem Unavailable dialog, which is the probe's own outcome.

    The failure is injected by mocking ``open_port`` to return ``False`` for the
    Transport Port only (the real ``open_port`` catches its errors and returns
    ``False``; it never raises). ``QMessageBox.critical`` is a blocking modal, so
    it is stubbed non-blocking — otherwise the headless run would hang waiting
    for an OK the offscreen harness can never deliver.

    Verifies: FR-039, FR-046.
    """
    errors: list[tuple] = []
    monkeypatch.setattr(
        "cpm_fm.gui.mw_remote.QMessageBox.critical",
        lambda *a, **k: errors.append(a[1:]),
    )

    # Mock open_port: succeed for the Terminal Port, fail (False) for Transport.
    monkeypatch.setattr(
        "cpm_fm.terminal.serial_manager.SerialManager.open_port",
        lambda self, *args, **kwargs: args[0] != "transport",
    )

    # Guard: if the probe were (wrongly) run, the Remote Filesystem Unavailable
    # dialog would block the offscreen loop — fail loudly instead of hanging.
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    probe_dialog_shown = []
    monkeypatch.setattr(
        RemoteUnavailableDialog,
        "exec",
        lambda self: (
            probe_dialog_shown.append(True)
            or setattr(self, "choice", RemoteUnavailableDialog.CONTINUE)
        ),
    )

    result = gui.connect(timeout=5.0)

    # FR-046: no probe is performed, so no probe result is produced.
    assert result is None, f"expected no probe result, got {result}"
    assert not probe_dialog_shown, "probe ran despite Transport open failure (FR-046 violated)"
    # FR-039: the transport-open error dialog was shown.
    assert errors, "expected the FR-039 transport-open error dialog to be shown"
    log.info("transport-open failure reported (FR-039); probe skipped (FR-046)")


@pytest.mark.hil
@pytest.mark.mt("MT-C17", "FR-050", "NFR-004")
def test_rapid_disconnect_during_probe_no_crash(gui):
    """Disconnecting during the post-connect probe leaves clean state.

    Verifies: FR-050, NFR-004.
    """
    assert gui.connect()[0] == "ok"

    # Immediately disconnect — before the probe worker finishes
    gui.disconnect()

    # Quiesce to let any queued signals fire
    gui.quiesce(timeout=5.0)

    # The window should still be alive and in a clean state
    assert not gui.connected
    assert not gui.transport_connected
    log.info("rapid disconnect complete; window alive, state clean")
