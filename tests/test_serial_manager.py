"""Unit tests for SerialManager.open_port parameter mapping.

These verify that the serial settings collected by the Serial Config dialog are
mapped onto the pyserial port correctly — in particular flow control (UIR-028),
which is exercised here for every dropdown value and for both the flat and
nested config-key shapes (NFR-002). The pyserial ``Serial`` class is replaced
with a capture stub so no real port is opened.
"""

import time

import pytest
import serial

import cpm_fm.terminal.serial_manager as sm_mod
from cpm_fm.terminal.serial_manager import SerialManager


class _CaptureSerial:
    """Stand-in for ``serial.Serial`` that records the kwargs it was built with.

    Provides a no-op ``in_waiting``/``read`` so the terminal read loop (started
    when a terminal port is opened) spins harmlessly instead of erroring."""

    last_kwargs: dict = {}
    in_waiting = 0

    def __init__(self, **kwargs):
        _CaptureSerial.last_kwargs = kwargs
        self.is_open = True

    def read(self, n: int = 1) -> bytes:
        return b""

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
    """UIR-028: the flat `flow` key maps to the matching pyserial handshake.

    Verifies: UIR-028.
    """
    mgr = SerialManager()
    ok = mgr.open_port("transport", {"transport_port": "COM1", "flow": flow})
    assert ok
    for key, value in expected.items():
        assert capture.last_kwargs[key] is value


def test_flow_control_nested_key(capture):
    """NFR-002: the nested `flow_control` key is honoured as a fallback.

    Verifies: NFR-002.
    """
    mgr = SerialManager()
    settings = {"serial": {"transfer_port": "COM4", "flow_control": "RTS/CTS"}}
    ok = mgr.open_port("transport", settings)
    assert ok
    assert capture.last_kwargs["rtscts"] is True
    assert capture.last_kwargs["xonxoff"] is False
    assert capture.last_kwargs["dsrdtr"] is False


def test_flow_control_defaults_off_when_absent(capture):
    """No flow setting -> all handshakes disabled (UIR-028 default NONE).

    Verifies: UIR-028.
    """
    mgr = SerialManager()
    ok = mgr.open_port("transport", {"transport_port": "COM1"})
    assert ok
    assert capture.last_kwargs["xonxoff"] is False
    assert capture.last_kwargs["rtscts"] is False
    assert capture.last_kwargs["dsrdtr"] is False


# --------------------------------------------------------------------------- #
# open_port: parity mapping, numeric coercion, key-shape fallbacks, failure.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("parity", "expected"),
    [
        ("NONE", serial.PARITY_NONE),
        ("ODD", serial.PARITY_ODD),
        ("EVEN", serial.PARITY_EVEN),
        ("MARK", serial.PARITY_MARK),
        ("SPACE", serial.PARITY_SPACE),
        ("even", serial.PARITY_EVEN),  # case-insensitive
        ("WHAT", serial.PARITY_NONE),  # unknown value falls back to NONE
    ],
)
def test_parity_maps_to_pyserial_constant(capture, parity, expected):
    """FR-030: each parity name maps to its pyserial constant; unknown -> NONE.

    Verifies: FR-030.
    """
    mgr = SerialManager()
    assert mgr.open_port("transport", {"transport_port": "COM1", "parity": parity})
    assert capture.last_kwargs["parity"] == expected


def test_numeric_fields_are_coerced_to_int(capture):
    """FR-030: speed/data/stopbits arrive as strings from the dialog and must be
    passed to pyserial as ints.

    Verifies: FR-030.
    """
    mgr = SerialManager()
    settings = {"transport_port": "COM1", "speed": "9600", "data": "7", "stopbits": "2"}
    assert mgr.open_port("transport", settings)
    assert capture.last_kwargs["baudrate"] == 9600
    assert capture.last_kwargs["bytesize"] == 7
    assert capture.last_kwargs["stopbits"] == 2
    for key in ("baudrate", "bytesize", "stopbits"):
        assert isinstance(capture.last_kwargs[key], int)


def test_nested_key_names_are_honoured(capture):
    """NFR-002: the nested settings shape uses transfer_port/data_bits/
    stop_bits, which must be read when the flat keys are absent.

    Verifies: NFR-002.
    """
    mgr = SerialManager()
    settings = {
        "serial": {
            "transfer_port": "COM9",
            "speed": "4800",
            "data_bits": "5",
            "stop_bits": "2",
        }
    }
    assert mgr.open_port("transport", settings)
    assert capture.last_kwargs["port"] == "COM9"
    assert capture.last_kwargs["bytesize"] == 5
    assert capture.last_kwargs["stopbits"] == 2


def test_numeric_defaults_applied_when_absent(capture):
    """FR-030: with no numeric settings the documented pyserial defaults apply.

    Verifies: FR-030.
    """
    mgr = SerialManager()
    assert mgr.open_port("transport", {"transport_port": "COM1"})
    assert capture.last_kwargs["baudrate"] == 115200
    assert capture.last_kwargs["bytesize"] == 8
    assert capture.last_kwargs["stopbits"] == 1


def test_read_timeout_defaults_to_100ms_when_absent(capture):
    """UIR-032/UIR-033: with no timeout setting, the port read timeout defaults
    to 0.1s (the previously hard-coded value).

    Verifies: UIR-032, UIR-033.
    """
    mgr = SerialManager()
    assert mgr.open_port("transport", {"transport_port": "COM1"})
    assert capture.last_kwargs["timeout"] == pytest.approx(0.1)


def test_read_timeout_is_per_port_and_converted_ms_to_seconds(capture):
    """UIR-032/UIR-033: each port reads its own millisecond timeout setting and
    passes it to pyserial in seconds.

    Verifies: UIR-032, UIR-033.
    """
    mgr = SerialManager()
    settings = {
        "terminal_port": "COM1",
        "transport_port": "COM2",
        "terminal_timeout_ms": "250",
        "transport_timeout_ms": "1500",
    }
    assert mgr.open_port("terminal", settings)
    assert capture.last_kwargs["timeout"] == pytest.approx(0.25)
    assert mgr.open_port("transport", settings)
    assert capture.last_kwargs["timeout"] == pytest.approx(1.5)


def test_read_timeout_falls_back_on_non_numeric_value(capture):
    """A malformed timeout value degrades to the 0.1s default rather than raising."""
    mgr = SerialManager()
    assert mgr.open_port("transport", {"transport_port": "COM1", "transport_timeout_ms": "abc"})
    assert capture.last_kwargs["timeout"] == pytest.approx(0.1)


def test_open_port_returns_false_on_serial_error(monkeypatch):
    """FR-030: a pyserial failure is caught and reported as False, leaving the
    connected flag clear (no half-open state).

    Verifies: FR-030.
    """

    def _boom(**kwargs):
        raise serial.SerialException("port busy")

    monkeypatch.setattr(sm_mod.serial, "Serial", _boom)
    mgr = SerialManager()
    assert mgr.open_port("transport", {"transport_port": "COM1"}) is False
    assert mgr.transport_connected is False
    assert mgr.transport_port is None


# --------------------------------------------------------------------------- #
# send_data and the port-close lifecycle.
# --------------------------------------------------------------------------- #


class _FakePort:
    """Minimal serial port double: records writes, can be opened/closed, and can
    be told to raise on close to exercise the failure branch."""

    def __init__(self, is_open=True, raise_on_close=False):
        self.is_open = is_open
        self.written = bytearray()
        self._raise_on_close = raise_on_close

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def close(self):
        if self._raise_on_close:
            raise OSError("cannot close")
        self.is_open = False


def test_send_data_writes_ascii_to_open_port():
    """FR-096: data is written to the selected open port and reports True.

    Verifies: FR-096.
    """
    mgr = SerialManager()
    mgr.terminal_port = _FakePort()
    assert mgr.send_data("terminal", "DIR\r") is True
    assert mgr.terminal_port.written == b"DIR\r"


def test_send_data_replaces_non_ascii():
    """FR-096: non-ASCII characters are replaced rather than raising.

    Verifies: FR-096.
    """
    mgr = SerialManager()
    mgr.transport_port = _FakePort()
    assert mgr.send_data("transport", "café") is True
    assert mgr.transport_port.written == b"caf?"


def test_send_data_returns_false_when_port_closed():
    """FR-096: with no open port the send reports False and writes nothing.

    Verifies: FR-096.
    """
    mgr = SerialManager()
    mgr.terminal_port = _FakePort(is_open=False)
    assert mgr.send_data("terminal", "DIR\r") is False
    assert mgr.terminal_port.written == b""


def test_send_data_returns_false_when_port_none():
    """FR-096: a missing port object reports False (no AttributeError).

    Verifies: FR-096.
    """
    mgr = SerialManager()
    assert mgr.send_data("transport", "x") is False


def test_close_terminal_port_closes_and_clears_flag():
    """FR-050/FR-052: closing the terminal port closes it and clears the flag.

    Verifies: FR-050, FR-052.
    """
    mgr = SerialManager()
    port = _FakePort()
    mgr.terminal_port = port
    mgr.terminal_connected = True
    assert mgr.close_terminal_port() is True
    assert port.is_open is False
    assert mgr.terminal_connected is False


def test_close_terminal_port_returns_false_on_error():
    """FR-052: a failure while closing is reported as False, not raised.

    Verifies: FR-052.
    """
    mgr = SerialManager()
    mgr.terminal_port = _FakePort(raise_on_close=True)
    mgr.terminal_connected = True
    assert mgr.close_terminal_port() is False


def test_close_transport_port_closes_and_clears_flag():
    """FR-055/FR-057: closing the transport port closes it and clears the flag.

    Verifies: FR-055, FR-057.
    """
    mgr = SerialManager()
    port = _FakePort()
    mgr.transport_port = port
    mgr.transport_connected = True
    assert mgr.close_transport_port() is True
    assert port.is_open is False
    assert mgr.transport_connected is False


def test_close_transport_port_returns_false_on_error():
    """FR-057: a failure while closing the transport port is reported as False.

    Verifies: FR-057.
    """
    mgr = SerialManager()
    mgr.transport_port = _FakePort(raise_on_close=True)
    mgr.transport_connected = True
    assert mgr.close_transport_port() is False


# --------------------------------------------------------------------------- #
# _read_loop dispatch and pause/resume (FR-036/FR-037).
# --------------------------------------------------------------------------- #


class _ReadOncePort:
    """Serial double that yields its seeded bytes once, then reads empty."""

    def __init__(self, data: bytes):
        self.is_open = True
        self._buf = bytearray(data)

    @property
    def in_waiting(self) -> int:
        return len(self._buf)

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk


def _run_read_loop_briefly(mgr, stop_when, max_ms=500):
    import threading

    t = threading.Thread(target=mgr._read_loop, daemon=True)
    t.start()
    waited = 0
    while not stop_when() and waited < max_ms:
        time.sleep(0.01)
        waited += 10
    mgr._stop_event.set()
    t.join(timeout=1.0)


def test_read_loop_dispatches_decoded_data():
    """FR-036/FR-091: bytes from the terminal port are decoded and pushed to the
    on_data_received callback.

    Verifies: FR-036, FR-091.
    """
    mgr = SerialManager()
    received: list[str] = []
    mgr.on_data_received = received.append
    mgr.terminal_port = _ReadOncePort(b"A>\r\n")
    _run_read_loop_briefly(mgr, stop_when=lambda: bool(received))
    assert received == ["A>\r\n"]


def test_read_loop_suspends_dispatch_while_paused():
    """FR-037: while paused the read loop consumes nothing, so a shared physical
    port can be handed to an X-Modem transfer without the loop stealing bytes.

    Verifies: FR-037.
    """
    mgr = SerialManager()
    received: list[str] = []
    mgr.on_data_received = received.append
    mgr.terminal_port = _ReadOncePort(b"DATA")
    mgr._read_paused.set()  # paused before the loop starts
    _run_read_loop_briefly(mgr, stop_when=lambda: False, max_ms=100)
    assert received == []
    assert mgr.terminal_port.in_waiting == 4  # nothing was consumed

    # After resuming, the same loop now delivers the bytes.
    mgr._stop_event.clear()
    mgr._read_paused.clear()
    _run_read_loop_briefly(mgr, stop_when=lambda: bool(received))
    assert received == ["DATA"]
