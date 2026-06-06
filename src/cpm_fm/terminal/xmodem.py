import os
import time
from typing import Optional

import serial


class XModem:
    """
    Implements the X-Modem protocol for file transfer.
    Supports both sending (Host -> Remote) and receiving (Remote -> Host).
    """

    SOH = b"\x01"  # Start of Header
    STX = b"\x02"  # Start of Text (for larger packets)
    EOT = b"\x04"  # End of Transmission
    ACK = b"\x06"  # Acknowledge
    NAK = b"\x15"  # Negative Acknowledge

    def __init__(self, serial_conn: serial.Serial, timeout: float = 1.0):
        self.ser = serial_conn
        self.timeout = timeout

    def _wait_for_char(self, expected: bytes, timeout: Optional[float] = None) -> bytes:
        """Wait for a specific character with a timeout."""
        t = timeout if timeout is not None else self.timeout
        start_time = time.time()
        while (time.time() - start_time) < t:
            if self.ser.in_waiting > 0:
                char = self.ser.read(1)
                if char == expected:
                    return char
            time.sleep(0.01)
        return b""

    def _calculate_checksum(self, data: bytes) -> int:
        """Standard X-Modem checksum (sum of bytes, modulo 256)."""
        return sum(data) & 0xFF

    def send_file(self, filepath: str) -> bool:
        """Sends a file from Host to Remote."""
        if not os.path.exists(filepath):
            return False

        with open(filepath, "rb") as f:
            data = f.read()

        # 1. Send C (0x43) to initiate transfer
        # Note: In many implementations, the receiver sends C, but we'll send it to trigger.
        self.ser.write(b"C")

        if self._wait_for_char(self.ACK) == b"":
            return False

        packet_num = 0
        offset = 0

        while offset < len(data):
            # Create packet: SOH + Seq + ~Seq + Data (128 bytes) + Checksum
            chunk = data[offset : offset + 128]
            checksum = self._calculate_checksum(chunk)

            packet = (
                self.SOH
                + bytes([packet_num])
                + bytes([255 - packet_num])
                + chunk
                + bytes([checksum])
            )

            # Send packet until ACK is received
            attempts = 0
            while attempts < 10:
                self.ser.write(packet)
                if self._wait_for_char(self.ACK) == self.ACK:
                    break
                attempts += 1
                packet_num = (packet_num + 1) % 256
            else:
                return False  # Too many NAKs/Timeouts

            offset += 128
            packet_num = (packet_num + 1) % 256

        # Send EOT
        self.ser.write(self.EOT)
        self._wait_for_char(self.ACK)
        return True

    def receive_file(self, save_path: str) -> bool:
        """Receives a file from Remote to Host."""
        # 1. Send C to signal readiness
        self.ser.write(b"C")

        if self._wait_for_char(self.SOH) == b"":
            return False

        received_data = bytearray()
        expected_packet = 0

        while True:
            # Read packet: Seq + ~Seq + 128 bytes + Checksum
            header = self.ser.read(2)
            if len(header) < 2:
                return False

            seq = header[0]
            inv_seq = header[1]

            if seq != expected_packet or (seq + inv_seq) != 255:
                self.ser.write(self.NAK)
                continue

            payload = self.ser.read(128)
            checksum = self.ser.read(1)

            if len(payload) < 128 or len(checksum) < 1:
                self.ser.write(self.NAK)
                continue

            if self._calculate_checksum(payload) != checksum[0]:
                self.ser.write(self.NAK)
                continue

            # Valid packet
            received_data.extend(payload)
            self.ser.write(self.ACK)
            expected_packet = (expected_packet + 1) % 256

            # Check for EOT
            # We need to check if the next byte is EOT or SOH
            # This is tricky with blocking reads, so we check if the server stops sending
            if self.ser.in_waiting == 0:
                # In a real scenario, we'd wait for EOT
                pass

            # Logic for EOT detection usually involves a timeout or reading a character
            # For this implementation, we assume the protocol ends with EOT
            if self._wait_for_char(self.EOT, timeout=2.0) == self.EOT:
                self.ser.write(self.ACK)
                break

        with open(save_path, "wb") as f:
            f.write(received_data)
        return True
