"""Unit tests for the pure serial-port selection helper (cpm_fm.utils.port_filter).

These exercise the host serial-port filtering/ordering that populates the Serial
Config dialog's Terminal/Transfer Port drop-downs (IFR-003, UIR-022/UIR-023),
and the "Show all ports" override (UIR-121), without a running Qt application or
real hardware (CR-014): a fake ``ListPortInfo`` stands in for ``comports()``
output so the phantom-legacy vs. real/USB distinction, the always-include of
configured ports, the empty-result fallback, and USB-first natural ordering are
all pinned down.

Satisfies: IFR-003, UIR-022, UIR-023, UIR-121, CR-014.
"""

from __future__ import annotations

from dataclasses import dataclass

from cpm_fm.utils.port_filter import is_phantom, select_ports


@dataclass
class FakePort:
    """Duck-typed stand-in for ``serial.tools.list_ports.ListPortInfo``."""

    device: str
    vid: int | None = None
    hwid: str = "n/a"


def _usb(device: str) -> FakePort:
    """A real USB serial adapter (carries a USB vendor id)."""
    return FakePort(device, vid=0x10C4, hwid="USB VID:PID=10C4:EA60")


def _phantom(device: str) -> FakePort:
    """An unbacked legacy node as Linux enumerates them (no vid, hwid 'n/a')."""
    return FakePort(device, vid=None, hwid="n/a")


def test_is_phantom_distinguishes_usb_from_legacy():
    """Verifies: IFR-003, UIR-022, UIR-023."""
    assert is_phantom(_phantom("/dev/ttyS4"))
    assert not is_phantom(_usb("/dev/ttyUSB0"))
    # An on-board port that reports a real hwid is not a phantom.
    assert not is_phantom(FakePort("/dev/ttyS0", vid=None, hwid="PNP0501"))
    # Empty hwid string is treated the same as the 'n/a' sentinel.
    assert is_phantom(FakePort("/dev/ttyS9", vid=None, hwid=""))


def test_phantom_ports_hidden_by_default():
    """Verifies: IFR-003, UIR-022, UIR-023."""
    ports = [_phantom(f"/dev/ttyS{n}") for n in range(4)] + [_usb("/dev/ttyUSB0")]
    assert select_ports(ports) == ["/dev/ttyUSB0"]


def test_show_all_reveals_phantom_ports():
    """Verifies: UIR-121."""
    ports = [_usb("/dev/ttyUSB0"), _phantom("/dev/ttyS0"), _phantom("/dev/ttyS1")]
    result = select_ports(ports, show_all=True)
    assert set(result) == {"/dev/ttyUSB0", "/dev/ttyS0", "/dev/ttyS1"}


def test_usb_ports_sorted_before_legacy_naturally():
    """Verifies: IFR-003, UIR-022, UIR-023."""
    ports = [
        _phantom("/dev/ttyS10"),
        _phantom("/dev/ttyS2"),
        _usb("/dev/ttyUSB10"),
        _usb("/dev/ttyUSB2"),
    ]
    # USB group first, each group in natural (numeric) order.
    assert select_ports(ports, show_all=True) == [
        "/dev/ttyUSB2",
        "/dev/ttyUSB10",
        "/dev/ttyS2",
        "/dev/ttyS10",
    ]


def test_always_include_keeps_configured_phantom_port():
    """Verifies: IFR-003, UIR-022, UIR-023."""
    ports = [_usb("/dev/ttyUSB0"), _phantom("/dev/ttyS4")]
    result = select_ports(ports, always_include=["/dev/ttyS4"])
    assert "/dev/ttyS4" in result
    assert "/dev/ttyUSB0" in result


def test_always_include_appends_absent_configured_port():
    """Verifies: IFR-003, UIR-022, UIR-023."""
    # A configured port that is no longer plugged in must still be offered.
    ports = [_usb("/dev/ttyUSB0")]
    result = select_ports(ports, always_include=["/dev/ttyACM9"])
    assert result == ["/dev/ttyUSB0", "/dev/ttyACM9"]


def test_empty_after_filtering_falls_back_to_all():
    """Verifies: IFR-003, UIR-022, UIR-023."""
    # Only phantoms present and none configured: show them rather than nothing.
    ports = [_phantom("/dev/ttyS0"), _phantom("/dev/ttyS1")]
    assert set(select_ports(ports)) == {"/dev/ttyS0", "/dev/ttyS1"}


def test_no_ports_returns_empty_list():
    """Verifies: IFR-003, UIR-022, UIR-023."""
    assert select_ports([]) == []
    assert select_ports([], show_all=True) == []


def test_plain_string_devices_supported():
    """Verifies: IFR-003 — helper is duck-typed and tolerates bare strings."""
    # Bare strings have no vid/hwid, so they read as phantom but survive via
    # the empty-fallback, and always_include still applies.
    assert select_ports(["COM1", "COM3"], show_all=True) == ["COM1", "COM3"]
