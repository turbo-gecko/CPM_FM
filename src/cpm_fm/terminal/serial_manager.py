import threading
import time
from typing import Callable, Optional

import serial


class SerialManager:
    """
    Manages serial communication for both Terminal and Transport ports.
    As per App_Design.md, handles the lifecycle and status flags of the ports.
    """

    def __init__(self):
        self.terminal_port: Optional[serial.Serial] = None
        self.transport_port: Optional[serial.Serial] = None

        self.terminal_connected = False
        self.transport_connected = False

        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.on_data_received: Optional[Callable[[str], None]] = None

    def open_port(self, port_type: str, settings: dict) -> bool:
        """
        Opens a serial port.
        port_type: 'terminal' or 'transport'
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
                # Try alternative key name from settings_a.json
                port_name = s.get("transfer_port" if port_type == "transport" else "terminal_port")

            params = {
                "port": port_name,
                "baudrate": int(s.get("speed", 115200)),
                "bytesize": int(s.get("data", s.get("data_bits", 8))),
                "stopbits": int(s.get("stopbits", s.get("stop_bits", 1))),
                "timeout": 0.1,
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
            print(f"Failed to open {port_type} port: {e}")
            return False

    def close_ports(self):
        """Closes both serial ports and stops the read thread."""
        self._stop_event.set()
        if self._read_thread:
            self._read_thread.join(timeout=1.0)

        if self.terminal_port and self.terminal_port.is_open:
            self.terminal_port.close()
        if self.transport_port and self.transport_port.is_open:
            self.transport_port.close()

        self.terminal_connected = False
        self.transport_connected = False

    def send_data(self, port_type: str, data: str) -> bool:
        """Sends data through the specified port."""
        port = self.terminal_port if port_type == "terminal" else self.transport_port
        if port and port.is_open:
            try:
                port.write(data.encode("ascii", errors="replace"))
                return True
            except Exception as e:
                print(f"Error sending data: {e}")
        return False

    def _read_loop(self):
        """Background thread to read data from the terminal port."""
        while not self._stop_event.is_set():
            if self.terminal_port and self.terminal_port.is_open:
                try:
                    if self.terminal_port.in_waiting > 0:
                        data = self.terminal_port.read(self.terminal_port.in_waiting).decode(
                            "ascii", errors="replace"
                        )
                        if self.on_data_received:
                            self.on_data_received(data)
                except Exception as e:
                    print(f"Read error: {e}")
            time.sleep(0.01)
