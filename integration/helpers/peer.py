"""``CpmPeer`` — headless control of the CP/M peer over the serial link.

The linchpin for protocol-tier reproducibility. It owns a real ``SerialManager``
on the terminal port (ports/baud read from the working-copy settings) and
reuses ``terminal/`` directly — no Qt, honouring CR-014 — to:

- capture command responses the way the app does (``_capture_terminal_response``),
- list / change drive / check existence via ``CPMParser``,
- run real X-Modem transfers in both directions, mirroring the app's launch
  sequence in ``mw_transfer_batches`` (issue the remote command on the terminal
  port, settle, then drive ``XModem`` over the transport port — pausing the
  terminal read loop when the two share one physical port, FR-037),
- seed / erase / wipe the **scratch** drive for state control.

All write operations are issued explicitly against an operator-nominated drive so
the peer never mutates a drive the test did not ask it to.
"""

from __future__ import annotations

import os
import time
from typing import Any

from cpm_fm.terminal.cpm_parser import CPMParser
from cpm_fm.terminal.serial_manager import SerialManager
from cpm_fm.terminal.xmodem import XModem

from .config import EOL_MAP
from .trace import get_logger, step

log = get_logger("peer")


class PeerError(RuntimeError):
    pass


class CpmPeer:
    """Drive a real CP/M machine for the HIL protocol tier."""

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.sm = SerialManager()
        self._capture_buf = ""
        self._capturing = False
        self.connect_drive: str | None = None  # the drive detected at connect
        self.eol = EOL_MAP.get(str(settings.get("eol", "CR")), "\r")

    # ----- lifecycle -------------------------------------------------------

    def _on_rx(self, data: str) -> None:
        if self._capturing:
            self._capture_buf += data

    def connect(self) -> CpmPeer:
        """Open the port(s) and probe the current CP/M drive prompt."""
        self.sm.on_data_received = self._on_rx
        term = self.settings.get("terminal_port")
        trans = self.settings.get("transport_port")
        shared = term == trans
        step(
            log,
            "connecting: terminal=%s transport=%s (%s)",
            term,
            trans,
            "shared port" if shared else "two-port",
        )
        if not self.sm.open_port("terminal", self.settings):
            raise PeerError(f"could not open terminal port {term!r}")
        if not shared:
            if not self.sm.open_port("transport", self.settings):
                self.sm.close_ports()
                raise PeerError(f"could not open transport port {trans!r}")
        else:
            # FR-037: shared physical port — point transport at the open terminal.
            self.sm.transport_port = self.sm.terminal_port
            self.sm.transport_connected = True
        self.connect_drive = self.detect_drive()
        drive = f"{self.connect_drive}:" if self.connect_drive else "(none)"
        step(log, "connected; CCP drive = %s", drive)
        return self

    def close(self) -> None:
        step(log, "closing ports")
        self.sm.close_ports()

    def __enter__(self) -> CpmPeer:
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def _shared_port(self) -> bool:
        return (
            self.sm.transport_port is not None and self.sm.transport_port is self.sm.terminal_port
        )

    # ----- terminal I/O ----------------------------------------------------

    def send_line(self, text: str) -> None:
        """Send ``text`` + the configured EOL on the terminal port (no capture)."""
        log.debug("→ %r", text)
        self.sm.send_data("terminal", text + self.eol)

    def capture(
        self,
        command: str,
        initial: float = 1.0,
        idle_window: float = 0.5,
        max_wait: float = 10.0,
    ) -> str:
        """Send ``command`` and capture the echoed output until it idles out.

        Mirrors ``MainWindow._capture_terminal_response`` (FR-075/FR-076): wait
        at least ``initial`` seconds, then until the receive buffer stops growing
        within ``idle_window``, bounded by ``max_wait``.
        """
        self._capture_buf = ""
        self._capturing = True
        try:
            self.send_line(command)
            time.sleep(initial)
            waited = initial
            while waited < max_wait:
                prev = len(self._capture_buf)
                time.sleep(idle_window)
                waited += idle_window
                if len(self._capture_buf) == prev:
                    break
            log.debug(
                "captured %d byte(s) in %.1fs for %r", len(self._capture_buf), waited, command
            )
            return self._capture_buf
        finally:
            self._capturing = False

    # ----- drive / listing -------------------------------------------------

    def detect_drive(self) -> str | None:
        """Send a bare EOL and return the current drive letter (FR-041/DR-033a)."""
        for _ in range(2):
            letter = CPMParser.drive_prompt_letter(self.capture(""))
            if letter:
                return letter
        return None

    def at_ccp_prompt(self) -> bool:
        return self.detect_drive() is not None

    def change_drive(self, letter: str) -> bool:
        """Switch the remote to ``letter`` (FR-100/FR-101). True if it took."""
        text = self.capture(f"{letter}:")
        ok = CPMParser.has_drive_prompt(text, letter)
        step(log, "change drive → %s: %s", letter, "ok" if ok else "FAILED")
        return ok

    def list(self, letter: str | None = None) -> dict[str, bool]:
        """Return the directory listing of ``letter`` (or the current drive)."""
        if letter is not None and not self.change_drive(letter):
            raise PeerError(f"drive {letter}: not available")
        cmd = self.settings.get("list_files_cmd", "DIR")
        listing = CPMParser.parse_dir_output(self.capture(cmd))
        step(log, "list %s → %d file(s)", f"{letter}:" if letter else "(current)", len(listing))
        return listing

    def exists(self, name: str, letter: str | None = None) -> bool:
        return name.upper() in {n.upper() for n in self.list(letter)}

    # ----- state control (writes target the given drive explicitly) --------

    def erase(self, name: str, letter: str | None = None) -> None:
        """Erase a single remote file (delete_remote_cmd) on ``letter``."""
        if letter is not None and not self.change_drive(letter):
            raise PeerError(f"drive {letter}: not available")
        template = self.settings.get("delete_remote_cmd", "ERA $1")
        if template:
            step(log, "erase %s on %s", name, f"{letter}:" if letter else "(current)")
            self.capture(template.replace("$1", name))

    def wipe_drive(self, letter: str) -> None:
        """Erase every file on ``letter`` (per-file ERA). DESTRUCTIVE.

        Mirrors the backup/restore wipe (FR-152/FR-153): list, then ERA each
        file by name. Always issued against the explicitly-passed drive.
        """
        if not self.change_drive(letter):
            raise PeerError(f"drive {letter}: not available")
        names = list(self.list())
        step(log, "WIPE %s: (%d file(s)) — DESTRUCTIVE", letter, len(names))
        for name in names:
            self.erase(name)

    def seed(self, local_paths: list[str], letter: str, use_1k: bool | None = None) -> None:
        """Upload a known set of files onto ``letter``. DESTRUCTIVE (writes)."""
        step(log, "seed %d file(s) → %s:", len(local_paths), letter)
        for path in local_paths:
            self.send_file(path, letter=letter, use_1k=use_1k)

    # ----- X-Modem transfers (mirror mw_transfer_batches) ------------------

    def _use_1k(self, override: bool | None) -> bool:
        if override is not None:
            return override
        return str(self.settings.get("xmodem_1k", "OFF")).upper() == "ON"

    def _issue_remote_cmd(self, kind: str, name: str, use_1k: bool) -> None:
        """Send the configured send/recv launch command (FR-087)."""
        if kind == "send":  # host -> remote (PCGET / XM R)
            std_key, default, k1k = "send_remote_cmd", "PCGET $1", "send_remote_cmd_1k"
        else:  # recv: remote -> host (PCPUT / XM S)
            std_key, default, k1k = "recv_remote_cmd", "PCPUT $1", "recv_remote_cmd_1k"
        if use_1k:
            t1k = str(self.settings.get(k1k, "")).strip()
            if t1k:
                self.send_line(t1k.replace("$1", name))
                return
        template = self.settings.get(std_key, default)
        if template:
            self.send_line(template.replace("$1", name))

    def _launch_delay(self) -> float:
        try:
            return max(0.0, float(self.settings.get("xfer_launch_delay", 3.0)))
        except (TypeError, ValueError):
            return 3.0

    def send_file(
        self,
        local_path: str,
        remote_name: str | None = None,
        letter: str | None = None,
        use_1k: bool | None = None,
    ) -> bool:
        """Upload one file host -> remote. Mirrors ``_send_one_to_remote``."""
        if letter is not None and not self.change_drive(letter):
            raise PeerError(f"drive {letter}: not available")
        if remote_name is None:
            remote_name = os.path.basename(local_path)
        use_1k = self._use_1k(use_1k)
        size = os.path.getsize(local_path) if os.path.exists(local_path) else -1
        step(
            log,
            "send %s → %s: [%s] (%d bytes)",
            remote_name,
            letter or "(current)",
            "1K" if use_1k else "128",
            size,
        )
        ser = self.sm.transport_port
        if self._shared_port:
            self.sm.pause_terminal_reads()
        try:
            if ser is not None:
                ser.reset_input_buffer()
            self._issue_remote_cmd("send", remote_name, use_1k)
            time.sleep(self._launch_delay())
            ok = XModem(ser).send_file(local_path, use_1k=use_1k)
            step(log, "send %s → %s", remote_name, "OK" if ok else "FAILED")
            return ok
        finally:
            if self._shared_port:
                self.sm.resume_terminal_reads()

    def recv_file(
        self,
        remote_name: str,
        save_path: str,
        letter: str | None = None,
        use_1k: bool | None = None,
    ) -> bool:
        """Download one file remote -> host. Mirrors ``_recv_one_to_host``."""
        if letter is not None and not self.change_drive(letter):
            raise PeerError(f"drive {letter}: not available")
        use_1k = self._use_1k(use_1k)
        step(
            log,
            "recv %s ← %s: [%s]",
            remote_name,
            letter or "(current)",
            "1K" if use_1k else "128",
        )
        ser = self.sm.transport_port
        if self._shared_port:
            self.sm.pause_terminal_reads()
        try:
            self._issue_remote_cmd("recv", remote_name, use_1k)
            time.sleep(self._launch_delay())
            ok = XModem(ser).receive_file(save_path, use_1k=use_1k)
            step(log, "recv %s → %s", remote_name, "OK" if ok else "FAILED")
            return ok
        finally:
            if self._shared_port:
                self.sm.resume_terminal_reads()
