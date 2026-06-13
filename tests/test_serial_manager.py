"""Unit tests for SerialManager.open_port parameter mapping.

These verify that the serial settings collected by the Serial Config dialog are
mapped onto the pyserial port correctly — in particular flow control (UIR-028),
which is exercised here for every dropdown value and for both the flat and
nested config-key shapes (NFR-002). The pyserial ``Serial`` class is replaced
with a capture stub so no real port is opened.
"""

import pytest

import cpm_fm.terminal.serial_manager as sm_mod
from cpm_fm.terminal.serial_manager import SerialManager


class _CaptureSerial:
    """Stand-in for ``serial.Serial`` that records the kwargs it was built with."""

    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        _CaptureSerial.last_kwargs = kwargs
        self.is_open = True

    def close(self):
        self.is_open = False


@pytest.fixture
def capture(monkeypatch):
    monkeypatch.setattr(sm_mod.serial, "Serial", _CaptureSerial)
    return _CaptureSerial


@pytest.mark.parametrize(
    ("flow", "expected"),
    [
        ("NONE", {"xonxoff": False, "rtscts": False, "dsrdtr": False}),
        ("XON/XOFF", {"xonxoff": True, "rtscts": False, "dsrdtr": False}),
        ("RTS/CTS", {"xonxoff": False, "rtscts": True, "dsrdtr": False}),
        ("DSR/DTR", {"xonxoff": False, "rtscts": False, "dsrdtr": True}),
    ],
)
def test_flow_control_flat_key(capture, flow, expected):
    """UIR-028: the flat `flow` key maps to the matching pyserial handshake."""
    mgr = SerialManager()
    ok = mgr.open_port("transport", {"transport_port": "COM1", "flow": flow})
    assert ok
    for key, value in expected.items():
        assert capture.last_kwargs[key] is value


def test_flow_control_nested_key(capture):
    """NFR-002: the nested `flow_control` key is honoured as a fallback."""
    mgr = SerialManager()
    settings = {"serial": {"transfer_port": "COM4", "flow_control": "RTS/CTS"}}
    ok = mgr.open_port("transport", settings)
    assert ok
    assert capture.last_kwargs["rtscts"] is True
    assert capture.last_kwargs["xonxoff"] is False
    assert capture.last_kwargs["dsrdtr"] is False


def test_flow_control_defaults_off_when_absent(capture):
    """No flow setting -> all handshakes disabled (UIR-028 default NONE)."""
    mgr = SerialManager()
    ok = mgr.open_port("transport", {"transport_port": "COM1"})
    assert ok
    assert capture.last_kwargs["xonxoff"] is False
    assert capture.last_kwargs["rtscts"] is False
    assert capture.last_kwargs["dsrdtr"] is False
