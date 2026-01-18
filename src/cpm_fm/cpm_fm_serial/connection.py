# connection.py
import serial
from cpm_fm.config.settings import get_serial_settings


class SerialConnection:
    def __init__(self):
        self.connection = None
        self.is_connected = False

    def connect(self):
        settings = get_serial_settings()
        try:
            self.connection = serial.Serial(
                port=settings['terminal_port'],      # Updated from 'comm_port' to 'terminal_port'
                baudrate=int(settings['speed']),
                bytesize=int(settings['data']),
                parity=settings['parity'].upper(),
                stopbits=int(settings['stopbits']),  # Updated key: 'stopbits' (not 'stop_bits')
                xonxoff=(settings['flow'] == 'XON/XOFF'),
                rtscts=(settings['flow'] == 'RTS/CTS')
            )
            self.is_connected = True
        except serial.SerialException as e:
            raise ConnectionError(f"Failed to connect: {str(e)}")

    def disconnect(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
            self.is_connected = False

    def send_command(self, command):
        if not self.is_connected:
            raise RuntimeError("Not connected")
        self.connection.write(command.encode())

    def receive_data(self, size=None, timeout=5):
        """
        Receive data from the serial port.

        Parameters:
            size (int, optional): Number of bytes to read. If None, reads all available bytes.
            timeout (float, optional): Override the default timeout for this read operation only.

        Returns:
            str: Decoded string from received bytes (UTF-8).
                Returns empty string if no data is received or connection is closed.

        Raises:
            RuntimeError: If not connected.
            UnicodeDecodeError: If received bytes cannot be decoded as UTF-8.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")

        # If timeout is specified, temporarily override the port's timeout
        original_timeout = self.connection.timeout
        if timeout is not None:
            self.connection.timeout = timeout

        try:
            if size is None:
                # Read all available bytes (non-blocking)
                data = self.connection.read(self.connection.in_waiting or 1)
            else:
                # Read exactly 'size' bytes, or until timeout
                data = self.connection.read(size)

            # Decode and return as string
            if data:
                return data.decode('utf-8')
            else:
                return ""  # No data received

        except UnicodeDecodeError as e:
            raise UnicodeDecodeError(f"Failed to decode serial data: {e}")
        finally:
            # Restore original timeout
            self.connection.timeout = original_timeout

    def send_data(self, data):
        """Send data over the serial connection."""
        if not self.is_connected:
            raise RuntimeError("Not connected")
        self.connection.write(data.encode())

    def get_available_ports(self):
        """Get a list of available serial ports."""
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def set_timeout(self, timeout):
        """Set the timeout for the connection."""
        if self.connection:
            self.connection.timeout = timeout

    def flush_input(self):
        """Flush input buffer."""
        if self.connection and self.connection.is_open:
            self.connection.flushInput()

    def flush_output(self):
        """Flush output buffer."""
        if self.connection and self.connection.is_open:
            self.connection.flushOutput()
