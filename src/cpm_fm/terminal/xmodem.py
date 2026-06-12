import os
import time
from typing import Callable, Optional

import serial


class XModem:
    """
    Implements the X-Modem protocol for file transfer.
    Supports both sending (Host -> Remote) and receiving (Remote -> Host).

    Satisfies: FR-082, NFR-003.
    """

    SOH = b"\x01"  # Start of Header
    STX = b"\x02"  # Start of Text (for larger packets)
    EOT = b"\x04"  # End of Transmission
    ACK = b"\x06"  # Acknowledge
    NAK = b"\x15"  # Negative Acknowledge
    PAD = 0x1A  # Final-packet padding byte (CP/M EOF / Ctrl-Z), see NFR-003

    def __init__(
        self,
        serial_conn: serial.Serial,
        timeout: float = 1.0,
        monitor: Optional[Callable[[str, bytes], None]] = None,
        progress: Optional[Callable[[int, int, Optional[int]], None]] = None,
    ):
        self.ser = serial_conn
        self.timeout = timeout
        # FR-086: optional observer invoked with ("tx"|"rx", data) for every
        # byte sent or received, so callers can echo the transfer to a display.
        self.monitor = monitor
        # FR-105: optional observer invoked once per accepted data packet with
        # (blocks, bytes_done, total_bytes) so callers can drive a progress
        # dialog. total_bytes is the file size when known (send_file) or None
        # when the protocol does not carry it (receive_file).
        self.progress = progress

    def _write(self, data: bytes) -> None:
        """Write bytes to the port, reporting them to the monitor (FR-086).

        Satisfies: FR-086.
        """
        self.ser.write(data)
        if self.monitor and data:
            self.monitor("tx", data)

    def _read(self, n: int) -> bytes:
        """Read up to n bytes from the port, reporting them to the monitor.

        Satisfies: FR-086.
        """
        data = self.ser.read(n)
        if self.monitor and data:
            self.monitor("rx", data)
        return data

    def _read_byte(self, timeout: Optional[float] = None) -> bytes:
        """Return the next byte to arrive within the timeout (b"" on timeout)."""
        t = timeout if timeout is not None else self.timeout
        start_time = time.time()
        while (time.time() - start_time) < t:
            if self.ser.in_waiting > 0:
                return self._read(1)
            time.sleep(0.01)
        return b""

    def _wait_for_one_of(
        self, expected: tuple[bytes, ...], timeout: Optional[float] = None
    ) -> bytes:
        """Wait for any byte in `expected`, discarding others (b"" on timeout)."""
        t = timeout if timeout is not None else self.timeout
        start_time = time.time()
        while (time.time() - start_time) < t:
            char = self._read_byte(timeout=t - (time.time() - start_time))
            if char and char in expected:
                return char
        return b""

    def _calculate_checksum(self, data: bytes) -> int:
        """Standard X-Modem checksum (sum of bytes, modulo 256).

        Satisfies: NFR-003.
        """
        return sum(data) & 0xFF

    def _crc16(self, data: bytes) -> int:
        """CRC-16/XMODEM (poly 0x1021, init 0x0000), used by CRC-mode senders
        such as PCGET/PCPUT. Transmitted big-endian as the 2-byte trailer.

        Satisfies: NFR-003.
        """
        crc = 0
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
                crc &= 0xFFFF
        return crc

    def _trailer(self, chunk: bytes, crc_mode: bool) -> bytes:
        """Build the packet trailer: 2-byte CRC-16 (CRC mode) or 1-byte
        checksum (checksum mode).

        Satisfies: NFR-003.
        """
        if crc_mode:
            crc = self._crc16(chunk)
            return bytes([(crc >> 8) & 0xFF, crc & 0xFF])
        return bytes([self._calculate_checksum(chunk)])

    def _trailer_ok(self, payload: bytes, trailer: bytes, crc_mode: bool) -> bool:
        """Validate a received packet trailer against the payload.

        Satisfies: NFR-003.
        """
        if crc_mode:
            return len(trailer) == 2 and ((trailer[0] << 8) | trailer[1]) == self._crc16(payload)
        return len(trailer) == 1 and trailer[0] == self._calculate_checksum(payload)

    def send_file(self, filepath: str) -> bool:
        """Sends a file from Host to Remote (e.g. into CP/M PCGET).

        X-Modem is receiver-driven: the sender waits for the receiver's start
        character before transmitting. That character also selects the mode —
        'C' (0x43) requests CRC, NAK (0x15) requests checksum — and we frame
        the trailer to match (NFR-003). 128-byte SOH packets either way.

        Satisfies: FR-081, FR-082, FR-083, FR-086, FR-105, NFR-003.
        """
        if not os.path.exists(filepath):
            return False

        with open(filepath, "rb") as f:
            data = f.read()

        # NB: do NOT flush the input buffer here. A receiver such as PCGET may
        # send its start character once, without repeating, and it can arrive
        # before this call runs; flushing would discard it. The caller clears
        # any stale bytes before launching the remote receiver instead.

        # 1. Wait for the receiver's start character and choose the mode from
        #    it. Receivers retransmit it periodically, so allow generous time.
        start = self._wait_for_one_of((b"C", self.NAK), timeout=60.0)
        if start == b"":
            return False
        crc_mode = start == b"C"

        total = len(data)
        packet_num = 1  # X-Modem data packets are numbered from 1.
        blocks = 0
        bytes_done = 0
        offset = 0

        while offset < len(data):
            # Create packet: SOH + Seq + ~Seq + Data (128 bytes) + trailer.
            # NFR-003: the final short chunk is padded to a full 128-byte data
            # field with the PAD byte before the trailer is computed.
            chunk = data[offset : offset + 128]
            real_len = len(chunk)  # bytes from the file, before padding
            if real_len < 128:
                chunk = chunk + bytes([self.PAD]) * (128 - real_len)

            packet = (
                self.SOH
                + bytes([packet_num])
                + bytes([255 - packet_num])
                + chunk
                + self._trailer(chunk, crc_mode)
            )

            # Send the packet, retransmitting the SAME packet on NAK/timeout.
            # The sequence number is fixed per packet and only advances on ACK.
            for _ in range(10):
                self._write(packet)
                if self._wait_for_one_of((self.ACK, self.NAK), timeout=2.0) == self.ACK:
                    break
            else:
                return False  # Too many NAKs/timeouts

            # FR-105: report progress once the packet is acknowledged.
            blocks += 1
            bytes_done += real_len
            if self.progress:
                self.progress(blocks, bytes_done, total)

            offset += 128
            packet_num = (packet_num + 1) % 256

        # Send EOT, retransmitting until the receiver ACKs it (bounded).
        for _ in range(10):
            self._write(self.EOT)
            if self._wait_for_one_of((self.ACK,), timeout=2.0) == self.ACK:
                break
        return True

    def receive_file(self, save_path: str) -> bool:
        """Receives a file from Remote to Host (e.g. from CP/M PCPUT).

        The CP/M-side senders (PCPUT V1.0) speak **checksum** X-Modem and do not
        understand the CRC start character 'C' — sending it makes them abort
        with "Unknown response from host". So we poll with NAK (checksum) first
        and only fall back to 'C' (CRC) if the sender does not answer NAK at all
        (NFR-003; "checksum mode, not CRC"). The mode is fixed by whichever
        prompt the sender answers. SOH frames carry 128 data bytes; STX frames
        carry 1024 (XMODEM-1K), so the 1K sender variants are accepted too.

        Satisfies: FR-081, FR-082, FR-083, FR-105, NFR-003.
        """
        received_data = bytearray()
        expected_packet = 1
        blocks = 0  # FR-105: count of accepted data packets, for progress

        # Drop any stale bytes (e.g. a CAN left from a previous aborted run)
        # so the first frame byte we read is genuinely the start of a packet.
        self.ser.reset_input_buffer()

        # 1. Establish the connection and the trailer mode. Try checksum (NAK)
        #    then CRC ('C'), waiting for the first frame byte (SOH/STX data, or
        #    EOT for an empty transfer). NAK is tried first because the CP/M
        #    senders are checksum-only and abort on a stray 'C'.
        char = b""
        crc_mode = False
        for prompt, is_crc in ((self.NAK, False), (b"C", True)):
            for _ in range(6):
                self._write(prompt)
                char = self._read_byte(timeout=3.0)
                if char in (self.SOH, self.STX, self.EOT):
                    crc_mode = is_crc
                    break
            if char in (self.SOH, self.STX, self.EOT):
                break
        else:
            return False

        while True:
            if char == self.EOT:
                self._write(self.ACK)
                break

            if char not in (self.SOH, self.STX):
                # Unexpected/garbage byte — NAK and wait for the next frame.
                self._write(self.NAK)
                char = self._read_byte(timeout=10.0)
                continue

            # Read the rest of the frame: Seq + ~Seq + data + trailer. SOH
            # frames hold 128 data bytes, STX frames hold 1024 (XMODEM-1K).
            size = 128 if char == self.SOH else 1024
            header = self._read(2)
            payload = self._read(size)
            trailer = self._read(2 if crc_mode else 1)

            if (
                len(header) < 2
                or len(payload) < size
                or (header[0] + header[1]) != 255
                or not self._trailer_ok(payload, trailer, crc_mode)
            ):
                self._write(self.NAK)
            else:
                # Store new packets; silently re-ACK a duplicate (the sender
                # may resend if our previous ACK was lost), per X-Modem.
                if header[0] == expected_packet:
                    received_data.extend(payload)
                    expected_packet = (expected_packet + 1) % 256
                    # FR-105: report progress for each newly stored packet. The
                    # X-Modem stream carries no length, so total_bytes is None;
                    # bytes_done counts received payload (incl. EOF padding).
                    blocks += 1
                    if self.progress:
                        self.progress(blocks, len(received_data), None)
                self._write(self.ACK)

            char = self._read_byte(timeout=10.0)

        with open(save_path, "wb") as f:
            f.write(received_data)
        return True
