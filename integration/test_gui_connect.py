"""§5 — GUI connect/disconnect over real serial (MT-C*).

Drives the real ``MainWindow`` against the live peer: Connect opens both ports,
the post-connect probe finds the drive and populates the Remote Files list;
Disconnect closes the ports and clears the list. The three-button "remote
unavailable" dialog (FR-044) and the forced-close failure (MT-C10) need an
unresponsive/uncloseable peer that a healthy bench rig can't produce on demand;
those stay covered by the unit suite (``tests/test_gui_smoke.py``) and manual
testing, and are noted in the README.

Deterministic port-open success and failure scenarios MT-C02--MT-C04 live in
``test_gui_connect_target_free.py`` so they run in CI without consuming a HIL
target. The rapid-connect/disconnect race exercises the probe-while-disconnect
path to verify no crash from a queued signal to a deleted QObject. The
swapped-ports disconnect regression (MT-C18, two-port only) configures the
Terminal/Transport ports back-to-front and asserts Disconnect stays prompt (the
bounded write timeout, FR-030, plus probe-cancel-on-disconnect, FR-050) instead
of stalling for tens of seconds.
"""

from __future__ import annotations

import time

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
@pytest.mark.mt("MT-C09", "FR-050", "FR-054", "FR-055", "FR-058")
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
@pytest.mark.req("FR-030", "FR-050")
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
@pytest.mark.req("FR-050", "NFR-004")
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


@pytest.mark.hil
@pytest.mark.two_port
@pytest.mark.mt("MT-C18", "FR-030", "FR-050")
def test_disconnect_prompt_with_ports_swapped(gui, monkeypatch):
    """Disconnect stays prompt when the Terminal/Transport ports are swapped.

    Regression for the misconfigured-port hang: with the two ports configured
    back-to-front the post-connect probe cannot reach the remote, and Disconnect
    used to stall for tens of seconds while the probe's serial I/O and the port
    close contended and an unbounded write drained. The bounded write timeout
    (FR-030) plus probe-cancel-on-disconnect (FR-050) keep it prompt. The Abort
    button on the Remote Filesystem Unavailable dialog drives the same
    ``do_disconnect`` path, so this bound covers that reported case too.

    Two-port targets only (single-port targets share one port, so there is
    nothing to swap). The probe failure would raise the modal Remote Filesystem
    Unavailable dialog, which the offscreen harness can never dismiss, so it is
    stubbed non-blocking (Continue).

    Verifies: FR-030, FR-050.
    """
    from cpm_fm.gui.remote_unavailable_dialog import RemoteUnavailableDialog

    monkeypatch.setattr(
        RemoteUnavailableDialog,
        "exec",
        lambda self: setattr(self, "choice", RemoteUnavailableDialog.CONTINUE),
    )

    # Configure the two ports back-to-front.
    term = gui.win.settings.get("terminal_port")
    trans = gui.win.settings.get("transport_port")
    assert term and trans and term != trans, "two-port target must have distinct ports"
    gui.win.settings["terminal_port"], gui.win.settings["transport_port"] = trans, term

    result = gui.connect(timeout=25.0)
    # The probe cannot reach the remote over the swapped link (failed, or the
    # terminal port never opened at all).
    assert result is None or result[0] == "failed", f"probe unexpectedly ok: {result}"

    start = time.time()
    gui.win.do_disconnect()
    elapsed = time.time() - start
    gui.quiesce()

    assert elapsed < 8.0, f"disconnect took {elapsed:.1f}s with ports swapped (expected prompt)"
    assert not gui.connected
    assert not gui.transport_connected
    log.info("swapped-port disconnect completed in %.2fs; state clean", elapsed)


@pytest.mark.hil
@pytest.mark.mt("MT-C19", "FR-017a", "FR-050")
def test_load_config_while_connected_closes_ports(gui):
    """Loading a configuration while connected closes the prior config's ports.

    Regression for the stale-connection bug: loading a new configuration used to
    leave the previously opened ports open while the status flags stayed set, so
    the app reported *connected* on ports that no longer matched the loaded
    config. ``load_config`` now runs the Disconnect close (FR-050–FR-058) before
    replacing the settings (FR-017a). Reloading the target's own settings file is
    enough to exercise the path — the fix keys off *being connected*, not on the
    ports differing.

    Verifies: FR-017a, FR-050.
    """
    assert gui.connect()[0] == "ok"
    assert gui.connected

    # Reload the same settings file the fixture loaded (recorded as last_config).
    gui.win.load_config(gui.win.window_state.last_config)
    gui.quiesce()

    # FR-017a: the prior configuration's ports were closed before the swap.
    assert not gui.connected, "terminal flag still set after loading a config while connected"
    assert not gui.transport_connected, "transport flag still set after loading a config"
    assert gui.remote_names() == []  # FR-017: stale listing cleared
    log.info("config load while connected closed the ports and cleared the list")
