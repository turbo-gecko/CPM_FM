"""Pure filtering and sorting helpers for host serial-port enumeration.

The Serial Configuration dialog's Terminal Port and Transfer Port drop-downs
(UIR-022/UIR-023) are populated by enumerating the host's serial ports
(IFR-003) with :func:`serial.tools.list_ports.comports`. On Linux the kernel
pre-registers a long run of legacy 8250/16550 nodes (``/dev/ttyS0`` …
``/dev/ttyS31``) that are almost never backed by real hardware, which buries the
USB adapters (``/dev/ttyUSB*``/``/dev/ttyACM*``) users actually want at the
bottom of an unwieldy list (GitHub issue #12).

This module holds the selection logic as pure functions operating on
``pyserial`` ``ListPortInfo``-like objects (duck-typed on ``device``, ``vid``
and ``hwid``), so it is unit-testable without a running Qt application and
imports nothing from the GUI toolkit (CR-014).

Selection semantics:
  * A port is treated as a **phantom** (an unbacked legacy node) when it reports
    no USB vendor id *and* no meaningful hardware id (``hwid`` empty or the
    ``pyserial`` "n/a" sentinel). Phantoms are hidden by default and revealed by
    ``show_all=True`` (the dialog's "Show all ports" toggle, UIR-121).
  * Any device named in ``always_include`` (the currently-configured ports) is
    kept even when it looks like a phantom, so a saved selection is never
    silently dropped from its drop-down.
  * If filtering would leave no ports at all, every enumerated port is returned
    instead, so the user is never locked out on an unusual host.
  * Surviving ports are ordered real/USB-backed first, then legacy, each group
    in natural device order (``ttyUSB2`` before ``ttyUSB10``).

Satisfies: IFR-003, UIR-022, UIR-023, UIR-121, CR-014.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

# ``pyserial`` fills unknown hardware ids with this literal rather than leaving
# them empty, so it is treated the same as "no hardware id" when spotting
# phantom ports.
_NO_HWID = "n/a"


def _device(info: Any) -> str:
    """Return a port's device path (``/dev/ttyUSB0``, ``COM3``, …).

    Duck-typed on the ``ListPortInfo.device`` attribute, falling back to the
    object's string form so plain strings work in tests and callers.
    """
    return str(getattr(info, "device", None) or info)


def is_phantom(info: Any) -> bool:
    """Return True if ``info`` looks like an unbacked legacy serial node.

    A phantom reports no USB vendor id (``vid is None``) *and* no meaningful
    hardware id — a real USB adapter always carries a ``vid``, and a genuine
    on-board port typically carries a non-trivial ``hwid``. This is a heuristic:
    the "Show all ports" toggle (UIR-121) and ``always_include`` are the safety
    valves for the rare host where it guesses wrong.

    Satisfies: IFR-003, UIR-022, UIR-023.
    """
    if getattr(info, "vid", None) is not None:
        return False
    hwid = (getattr(info, "hwid", "") or "").strip().lower()
    return hwid in ("", _NO_HWID)


def _natural_key(device: str) -> list:
    """Sort key that orders embedded numbers numerically (``ttyS2`` < ``ttyS10``)."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", device)]


def select_ports(
    port_infos: Iterable[Any],
    *,
    show_all: bool = False,
    always_include: Sequence[str] = (),
) -> list[str]:
    """Return the device paths to offer in the port drop-downs.

    ``port_infos`` is the ``comports()`` result (or any iterable of
    ``ListPortInfo``-like objects). With ``show_all`` false, phantom ports
    (:func:`is_phantom`) are hidden unless named in ``always_include``; with it
    true, every port is offered. If filtering empties the list the full set is
    returned instead. The result is ordered real/USB-backed first, then legacy,
    each group in natural device order, and any ``always_include`` device absent
    from the enumeration is appended so a configured-but-unplugged port still
    appears.

    Satisfies: IFR-003, UIR-022, UIR-023, UIR-121.
    """
    infos = list(port_infos)
    always = set(always_include)

    if show_all:
        kept = infos
    else:
        kept = [i for i in infos if not is_phantom(i) or _device(i) in always]
        # Never leave the user with an empty list on an unusual host.
        if not kept:
            kept = infos

    kept_sorted = sorted(kept, key=lambda i: (is_phantom(i), _natural_key(_device(i))))
    devices = [_device(i) for i in kept_sorted]

    # A configured port that is no longer present must still be selectable so
    # loading its config does not silently switch ports.
    seen = set(devices)
    for dev in always_include:
        if dev and dev not in seen:
            devices.append(dev)
            seen.add(dev)

    return devices
