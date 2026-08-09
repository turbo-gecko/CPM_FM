"""Capability-gated physical flow-control interoperability coverage."""

from __future__ import annotations

import pytest
from helpers.integrity import assert_round_trip
from helpers.peer import CpmPeer

pytestmark = [pytest.mark.hil, pytest.mark.flow_control, pytest.mark.best_effort]


def _serial_settings(settings: dict) -> dict:
    """Return the flat serial settings accepted by ``SerialManager``."""
    serial_settings = settings.get("serial")
    return serial_settings if isinstance(serial_settings, dict) else settings


@pytest.mark.mt("MT-P05", "UIR-028")
def test_rtscts_peer_completes_byte_exact_round_trip(target, scratch_drive, tmp_path):
    """RTS/CTS reaches the real ports and permits a live byte-exact transfer.

    The target capability is an operator assertion backed by a stalled NONE
    run or serial-line-monitor observation. This test independently proves that
    CPM-FM applies RTS/CTS to every distinct real port and interoperates with
    that declared flow-control-sensitive peer.

    Verifies: UIR-028.
    """
    settings = target.load_settings()
    serial_settings = _serial_settings(settings)
    flow = str(serial_settings.get("flow", serial_settings.get("flow_control", "NONE"))).upper()
    if flow != "RTS/CTS":
        pytest.skip(
            f"BLOCKED: target {target.name!r} declares flow_control_peer=true "
            f"but its app settings use Flow={flow!r}, not 'RTS/CTS'"
        )

    remote_name = "FLOWCTL.BIN"
    source = tmp_path / remote_name
    received = tmp_path / "received.bin"
    payload = bytes(range(256)) + b"CPM-FM RTS/CTS HIL\r\n"
    source.write_bytes(payload)

    peer = CpmPeer(settings)
    original_drive = None
    connected = False
    scratch_selected = False
    try:
        peer.connect()
        connected = True
        original_drive = peer.connect_drive
        if original_drive is None:
            pytest.skip(
                f"BLOCKED: target {target.name!r} opened its serial ports but "
                "returned no recognisable CP/M drive prompt"
            )

        ports = {id(port): port for port in (peer.sm.terminal_port, peer.sm.transport_port)}
        assert ports, "the live connection exposed no serial port objects"
        for port in ports.values():
            assert port is not None and port.is_open, "a configured serial port is not open"
            assert port.rtscts is True, "RTS/CTS was not applied to a live serial port"
            assert port.xonxoff is False, "XON/XOFF was unexpectedly enabled with RTS/CTS"
            assert port.dsrdtr is False, "DSR/DTR was unexpectedly enabled with RTS/CTS"

        if not peer.change_drive(scratch_drive):
            pytest.skip(
                f"BLOCKED: target {target.name!r} could not select its declared "
                f"scratch drive {scratch_drive}:"
            )
        scratch_selected = True
        peer.erase(remote_name)
        assert peer.send_file(str(source), letter=scratch_drive, use_1k=False), (
            "upload did not complete through the RTS/CTS-configured peer"
        )
        assert peer.exists(remote_name, letter=scratch_drive), (
            f"{remote_name} was not listed after the RTS/CTS upload"
        )
        assert peer.recv_file(remote_name, str(received), letter=scratch_drive, use_1k=False), (
            "download did not complete through the RTS/CTS-configured peer"
        )
        assert_round_trip(source, received)
    finally:
        if connected:
            try:
                if scratch_selected:
                    peer.erase(remote_name, letter=scratch_drive)
                if original_drive and original_drive != scratch_drive.upper():
                    peer.change_drive(original_drive)
            finally:
                peer.close()
