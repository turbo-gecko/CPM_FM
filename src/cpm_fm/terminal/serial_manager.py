import threading
import time
from typing import Callable, Optional

import serial


class SerialManager:
    """
    Manages serial communication for both Terminal and Transport ports.
    Handles the port lifecycle and status flags (SRS docs/cpm_fm_requirements.md,
    FR-001/FR-002 status flags, FR-030-FR-057 connect/disconnect, NFR-001/NFR-002).

    Satisfies: IFR-001, IFR-002.
    """

    def __init__(self):
        """
        Satisfies: FR-001, FR-002.
        """
        self.terminal_port: Optional[serial.Serial] = None
        self.transport_port: Optional[serial.Serial] = None

        self.terminal_connected = False
        self.transport_connected = False

        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # When set, the read loop stops consuming bytes from the terminal port
        # so an X-Modem transfer can take exclusive ownership of it. This is
        # required when the Transport Port and Terminal Port are the same
        # physical port (FR-037): otherwise the read loop and X-Modem race for
        # the same incoming bytes.
        self._read_paused = threading.Event()
        # Delivers raw bytes read from the Terminal Port. Decoding is deferred to
        # the consumer (mw_remote.handle_terminal_recv), which tees the bytes to
        # the VT-100 engine (which needs raw bytes) and, decoded, to the receive/
        # capture buffers. Keeping bytes here avoids lossy early ASCII decoding.
        self.on_data_received: Optional[Callable[[bytes], None]] = None

    def open_port(self, port_type: str, settings: dict) -> bool:
        """
        Opens a serial port.
        port_type: 'terminal' or 'transport'

        Satisfies: FR-030, FR-032, FR-033, FR-038, FR-040, UIR-028, UIR-032, UIR-033, NFR-002.
        """
        try:
            # Map settings to pyserial parameters
            # Note: Settings might be in a nested 'serial' dict or flat
            s = (
                settings.get("serial", settings)
                if isinstance(settings, dict) and "serial" in settings
                else settings
            )

            # Determine which port name to use
            port_name = s.get("terminal_port" if port_type == "terminal" else "transport_port")
            if not port_name:
                # Try alternative key name from the nested settings shape
                port_name = s.get("transfer_port" if port_type == "transport" else "terminal_port")

            # Per-port read timeout (UIR-032/UIR-033). Stored in milliseconds in
            # the config; pyserial wants seconds. Each port reads its own key,
            # falling back to the 100 ms default that was previously hard-coded.
            timeout_key = (
                "terminal_timeout_ms" if port_type == "terminal" else "transport_timeout_ms"
            )
            try:
                timeout_ms = int(s.get(timeout_key, 100))
            except (TypeError, ValueError):
                timeout_ms = 100
            # Bounded write timeout (FR-030/FR-038). Without it a write — and the
            # port close that waits for pending output to drain — can block
            # indefinitely when the link cannot transmit (e.g. the Terminal and
            # Transport ports are configured back-to-front, or a configured
            # hardware handshake line is never asserted), which used to stall
            # Disconnect for tens of seconds. Stored in milliseconds; pyserial
            # wants seconds. Default 2000 ms.
            write_timeout_key = (
                "terminal_write_timeout_ms"
                if port_type == "terminal"
                else "transport_write_timeout_ms"
            )
            try:
                write_timeout_ms = int(s.get(write_timeout_key, 2000))
            except (TypeError, ValueError):
                write_timeout_ms = 2000
            params = {
                "port": port_name,
                "baudrate": int(s.get("speed", 115200)),
                "bytesize": int(s.get("data", s.get("data_bits", 8))),
                "stopbits": int(s.get("stopbits", s.get("stop_bits", 1))),
                "timeout": max(0.01, timeout_ms / 1000.0),
                "write_timeout": max(0.1, write_timeout_ms / 1000.0),
            }

            # Handle parity mapping for pyserial
            parity_val = s.get("parity", "NONE").upper()
            parity_map = {
                "NONE": serial.PARITY_NONE,
                "ODD": serial.PARITY_ODD,
                "EVEN": serial.PARITY_EVEN,
                "MARK": serial.PARITY_MARK,
                "SPACE": serial.PARITY_SPACE,
            }
            params["parity"] = parity_map.get(parity_val, serial.PARITY_NONE)

            # UIR-028: apply the configured flow control. The flat config shape
            # uses the key `flow`, the nested shape uses `flow_control`; fall
            # back across both (NFR-002). An unknown value (or NONE) leaves all
            # three handshakes disabled.
            flow_val = str(s.get("flow", s.get("flow_control", "NONE"))).upper()
            params["xonxoff"] = flow_val == "XON/XOFF"
            params["rtscts"] = flow_val == "RTS/CTS"
            params["dsrdtr"] = flow_val == "DSR/DTR"

            if port_type == "terminal":
                self.terminal_port = serial.Serial(**params)
                self.terminal_connected = True
                # Start reading thread for terminal
                self._stop_event.clear()
                self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
                self._read_thread.start()
            else:
                self.transport_port = serial.Serial(**params)
                self.transport_connected = True

            return True
        except Exception as e:
            # FR-033/FR-040: on a failed open, explicitly clear the matching
            # status flag rather than relying on it never having been set.
            if port_type == "terminal":
                self.terminal_connected = False
            else:
                self.transport_connected = False
            print(f"Failed to open {port_type} port: {e}")
            return False

    @staticmethod
    def _purge_before_close(port) -> None:
        """Best-effort discard of queued I/O immediately before closing a port.

        On Windows, ``CloseHandle`` on a serial port can block waiting for the
        driver's queued transmit bytes to drain. Under hardware (RTS/CTS) or
        software (XON/XOFF) flow control that never completes when the peer
        stops asserting CTS / sends XOFF — e.g. the Terminal and Transport ports
        are configured back-to-front, so bytes the connect probe queued can
        never leave — and the close (and therefore Disconnect) stalls for tens
        of seconds. The pyserial ``write_timeout`` bounds ``WriteFile`` calls but
        not this close-time flush, so it is not enough on its own.

        ``reset_output_buffer`` issues ``PurgeComm`` with ``PURGE_TXABORT |
        PURGE_TXCLEAR``, aborting the pending write and discarding the queued
        transmit bytes so ``close()`` returns promptly; the receive buffer is
        dropped too. Best-effort: ports/stubs without these methods (or an
        already-detached port) are ignored. This mirrors the X-Modem cancel
        abort's flow-control-safe drain (``xmodem.py:_abort``).

        Satisfies: FR-050, FR-055.
        """
        try:
            port.reset_output_buffer()
            port.reset_input_buffer()
        except Exception:
            pass

    def close_ports(self):
        """
        Closes both serial ports and stops the read thread.

        Satisfies: FR-015, FR-050, FR-055.
        """
        self._stop_event.set()
        if self._read_thread:
            self._read_thread.join(timeout=1.0)

        if self.terminal_port and self.terminal_port.is_open:
            self._purge_before_close(self.terminal_port)
            self.terminal_port.close()
        if self.transport_port and self.transport_port.is_open:
            self._purge_before_close(self.transport_port)
            self.transport_port.close()

        self.terminal_connected = False
        self.transport_connected = False

    def close_terminal_port(self) -> bool:
        """
        Closes the Terminal Port and stops the read thread (FR-050-FR-053).
        Returns True if the port was closed (or was already closed), False if
        the close attempt raised an error.

        Satisfies: FR-050, FR-052.
        """
        try:
            self._stop_event.set()
            if self._read_thread:
                self._read_thread.join(timeout=1.0)
                self._read_thread = None
            if self.terminal_port and self.terminal_port.is_open:
                self._purge_before_close(self.terminal_port)
                self.terminal_port.close()
            self.terminal_connected = False
            return True
        except Exception as e:
            print(f"Failed to close terminal port: {e}")
            return False

    def close_transport_port(self) -> bool:
        """
        Closes the Transport Port (FR-055-FR-057). Returns True on success
        (or if already closed), False if the close attempt raised an error.

        Satisfies: FR-055, FR-057.
        """
        try:
            if self.transport_port and self.transport_port.is_open:
                self._purge_before_close(self.transport_port)
                self.transport_port.close()
            self.transport_connected = False
            return True
        except Exception as e:
            print(f"Failed to close transport port: {e}")
            return False

    def pause_terminal_reads(self) -> None:
        """Suspend the terminal read loop so a transfer can own the port.

        Needed only when the Transport and Terminal Ports are the same physical
        port (FR-037): X-Modem and the read loop would otherwise both consume
        incoming bytes. Returns once an in-flight read cycle has had time to
        finish, so the caller can rely on having exclusive access afterwards.

        Satisfies: FR-037, FR-083, NFR-001.
        """
        self._read_paused.set()
        # Let any read iteration already past the pause check complete; the loop
        # body reads then sleeps 0.01s, so this comfortably covers one cycle.
        time.sleep(0.05)

    def resume_terminal_reads(self) -> None:
        """Resume the terminal read loop after a transfer (see
        ``pause_terminal_reads``).

        Satisfies: FR-037, FR-083, NFR-001.
        """
        self._read_paused.clear()

    def send_data(self, port_type: str, data: str) -> bool:
        """
        Sends data through the specified port.

        Satisfies: FR-096.
        """
        port = self.terminal_port if port_type == "terminal" else self.transport_port
        if port and port.is_open:
            try:
                port.write(data.encode("ascii", errors="replace"))
                return True
            except Exception as e:
                print(f"Error sending data: {e}")
        return False

    def send_raw(self, port_type: str, data: bytes) -> bool:
        """
        Sends raw bytes through the specified port, unchanged.

        Unlike :meth:`send_data` (which ASCII-encodes a string), this writes the
        given bytes verbatim, so control characters above 0x7F survive intact.
        Used by the boot-sequence ``SENDRAW`` directive (FR-047) for keys such as
        Ctrl-C (0x03) or ESC (0x1B).

        Satisfies: FR-047.
        """
        port = self.terminal_port if port_type == "terminal" else self.transport_port
        if port and port.is_open:
            try:
                port.write(data)
                return True
            except Exception as e:
                print(f"Error sending raw data: {e}")
        return False

    def _read_loop(self):
        """
        Background thread to read data from the terminal port.

        Delivers the bytes read verbatim to ``on_data_received`` (no decoding).
        The consumer decodes for the receive/capture buffers and feeds the raw
        bytes to the VT-100 engine, which relies on byte-accurate input.

        Satisfies: FR-036, FR-091, NFR-001.
        """
        while not self._stop_event.is_set():
            if not self._read_paused.is_set() and self.terminal_port and self.terminal_port.is_open:
                try:
                    if self.terminal_port.in_waiting > 0:
                        data = self.terminal_port.read(self.terminal_port.in_waiting)
                        if self.on_data_received:
                            self.on_data_received(data)
                except Exception as e:
                    print(f"Read error: {e}")
            time.sleep(0.01)
