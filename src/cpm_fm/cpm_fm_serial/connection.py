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
                port=settings['comm_port'],
                baudrate=int(settings['speed']),
                bytesize=int(settings['data']),
                parity=settings['parity'].upper(),
                stopbits=int(settings['stop_bits']),
                xonxoff=(settings['flow_control'] == 'XON/XOFF'),
                rtscts=(settings['flow_control'] == 'RTS/CTS')
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
