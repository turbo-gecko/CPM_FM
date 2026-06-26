import os
import time
from typing import Callable, Optional

import serial


class XModem:
    """
    Implements the X-Modem protocol for file transfer.
    Supports both sending (Host -> Remote) and receiving (Remote -> Host).

    Satisfies: FR-082, NFR-003a, NFR-003b, NFR-003c, NFR-003d, NFR-003e, NFR-003f,
        NFR-003g, NFR-003h, NFR-003i, NFR-003j, NFR-003k, NFR-003l, NFR-003m, NFR-003n, NFR-003o.
    """

    SOH = b"\x01"  # Start of Header
    STX = b"\x02"  # Start of Text (for larger packets)
    EOT = b"\x04"  # End of Transmission
    ACK = b"\x06"  # Acknowledge
    NAK = b"\x15"  # Negative Acknowledge
    CAN = b"\x18"  # Cancel (X-Modem abort), see FR-120/NFR-003m
    PAD = 0x1A  # Final-packet padding byte (CP/M EOF / Ctrl-Z), see NFR-003c

    def __init__(
        self,
        serial_conn: serial.Serial,
        timeout: float = 1.0,
        monitor: Optional[Callable[[str, bytes], None]] = None,
        progress: Optional[Callable[[int, int, Optional[int]], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
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
        # FR-120: optional predicate polled during the transfer; when it returns
        # True the transfer is aborted (CAN sent to the remote) and the
        # send/receive call returns False. Set from a thread-safe flag by the
        # caller so a GUI Cancel button can interrupt the worker thread.
        self.cancel_check = cancel_check

    def _cancelled(self) -> bool:
        """Whether cancellation has been requested (FR-120).

        Satisfies: FR-120.
        """
        return self.cancel_check is not None and self.cancel_check()

    def _abort(self) -> None:
        """Abort the transfer by sending the X-Modem CAN sequence (FR-120).

        Several CAN bytes are sent so the remote reliably recognises the abort.
        The serial port is then flushed in BOTH directions so the cancellation
        takes effect immediately: any partially-transmitted packet still queued
        for transmit is discarded (otherwise it keeps draining to the remote
        after the cancel), and any data the remote was still sending mid-abort
        is dropped from the receive buffer. Without this, the transfer appears
        to keep going until the buffers empty (FR-120).

        The wait for the CAN bytes to leave the port is **bounded** (see
        :meth:`_drain_tx`): a plain ``serial.Serial.flush()`` busy-waits on
        ``out_waiting`` with no timeout, so if the line cannot drain — e.g.
        hardware (RTS/CTS) or software (XON/XOFF) flow control stalls because
        the aborting remote has stopped asserting CTS / sent XOFF — it would
        block the transfer worker thread forever. That left the modal progress
        dialog stuck open with its Cancel button disabled and no close button,
        with no way to dismiss it (FR-120).

        Satisfies: FR-120, NFR-003m, NFR-003n.
        """
        try:
            # Discard the in-flight packet still queued for transmit so it does
            # not keep draining to the remote after the cancel.
            self.ser.reset_output_buffer()
            # Tell the remote to abort, then wait (bounded) for the CAN bytes to
            # go out before dropping the line quiet.
            self._write(self.CAN * 3)
            self._drain_tx(timeout=1.0)
            # Drop anything the remote was still sending mid-abort.
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def _drain_tx(self, timeout: float) -> None:
        """Wait, bounded by ``timeout`` seconds, for the port's queued transmit
        bytes (the CAN sequence) to leave before the abort returns (FR-120).

        Unlike ``serial.Serial.flush()`` — which busy-waits on ``out_waiting``
        with no bound — this gives up once the timeout elapses, so a stalled
        line (flow control de-asserted by an aborting remote) can never hang the
        transfer worker thread. Any CAN bytes still queued when the wait gives
        up are transmitted by the OS in the background while the (shared
        transport) port remains open, so the remote still receives the abort.
        Ports/stubs without an ``out_waiting`` attribute fall back to a single
        best-effort ``flush()``.

        Satisfies: FR-120, NFR-003o.
        """
        if not hasattr(self.ser, "out_waiting"):
            try:
                self.ser.flush()
            except Exception:
                pass
            return
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if not self.ser.out_waiting:
                    return
            except Exception:
                return
            time.sleep(0.02)

    def _write(self, data: bytes) -> None:
        """
        Write bytes to the port, reporting them to the monitor (FR-086).

        Satisfies: FR-086.
        """
        self.ser.write(data)
        if self.monitor and data:
            self.monitor("tx", data)

    def _read(self, n: int) -> bytes:
        """
        Read up to n bytes from the port, reporting them to the monitor.

        Satisfies: FR-086.
        """
        data = self.ser.read(n)
        if self.monitor and data:
            self.monitor("rx", data)
        return data

    def _read_exact(self, n: int, idle_timeout: float = 3.0) -> bytes:
        """Read exactly ``n`` bytes, reassembling them across several underlying
        reads if necessary.

        The transport port is opened with a short read timeout (0.1s), so a
        single ``ser.read(n)`` returns only the bytes that happened to arrive in
        that window — for a 1024-byte XMODEM-1K frame that is far fewer than ``n``
        at any normal baud rate, which truncates the frame and desynchronises the
        stream (a stray byte downstream then reads as EOT and ends the transfer
        early). This accumulates until ``n`` bytes have arrived, giving up only
        after ``idle_timeout`` seconds elapse with no new byte (a genuine stall)
        or on cancellation (FR-120), returning whatever was gathered.

        Satisfies: FR-082, FR-086, NFR-003i.
        """
        buf = bytearray()
        last = time.time()
        while len(buf) < n:
            if self._cancelled():
                break
            chunk = self.ser.read(n - len(buf))
            if chunk:
                buf += chunk
                last = time.time()
            elif (time.time() - last) >= idle_timeout:
                break
            else:
                time.sleep(0.005)
        data = bytes(buf)
        if self.monitor and data:
            self.monitor("rx", data)
        return data

    def _read_byte(self, timeout: Optional[float] = None) -> bytes:
        """
        Return the next byte to arrive within the timeout (b"" on timeout).
        """
        t = timeout if timeout is not None else self.timeout
        start_time = time.time()
        while (time.time() - start_time) < t:
            # FR-120: end long waits promptly when cancellation is requested.
            if self._cancelled():
                return b""
            if self.ser.in_waiting > 0:
                return self._read(1)
            time.sleep(0.01)
        return b""

    def _wait_for_one_of(
        self, expected: tuple[bytes, ...], timeout: Optional[float] = None
    ) -> bytes:
        """
        Wait for any byte in `expected`, discarding others (b"" on timeout).
        """
        t = timeout if timeout is not None else self.timeout
        start_time = time.time()
        while (time.time() - start_time) < t:
            # FR-120: bail out of the wait promptly when cancellation is
            # requested (otherwise _read_byte returns b"" instantly and this
            # loop would spin for the whole timeout before the caller aborts).
            if self._cancelled():
                return b""
            char = self._read_byte(timeout=t - (time.time() - start_time))
            if char and char in expected:
                return char
        return b""

    def _calculate_checksum(self, data: bytes) -> int:
        """Standard X-Modem checksum (sum of bytes, modulo 256).

        Satisfies: NFR-003d.
        """
        return sum(data) & 0xFF

    def _crc16(self, data: bytes) -> int:
        """CRC-16/XMODEM (poly 0x1021, init 0x0000), used by CRC-mode senders
        such as PCGET/PCPUT. Transmitted big-endian as the 2-byte trailer.

        Satisfies: NFR-003e.
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

        Satisfies: NFR-003d, NFR-003e.
        """
        if crc_mode:
            crc = self._crc16(chunk)
            return bytes([(crc >> 8) & 0xFF, crc & 0xFF])
        return bytes([self._calculate_checksum(chunk)])

    def _trailer_ok(self, payload: bytes, trailer: bytes, crc_mode: bool) -> bool:
        """Validate a received packet trailer against the payload.

        Satisfies: NFR-003d, NFR-003e, NFR-003l.
        """
        if crc_mode:
            return len(trailer) == 2 and ((trailer[0] << 8) | trailer[1]) == self._crc16(payload)
        return len(trailer) == 1 and trailer[0] == self._calculate_checksum(payload)

    def send_file(self, filepath: str, use_1k: bool = False) -> bool:
        """Sends a file from Host to Remote (e.g. into CP/M PCGET).

        X-Modem is receiver-driven: the sender waits for the receiver's start
        character before transmitting. That character also selects the mode —
        'C' (0x43) requests CRC, NAK (0x15) requests checksum — and we frame
        the trailer to match (NFR-003d, NFR-003e). When ``use_1k`` is True the
        data field is 1024 bytes framed with STX (XMODEM-1K); otherwise it is 128
        bytes framed with SOH. The frame size is independent of the CRC/checksum mode.

        Satisfies: FR-081, FR-082, FR-083, FR-086, FR-105, FR-120, NFR-003a, NFR-003b, NFR-003c.
        """
        if not os.path.exists(filepath):
            return False

        # XMODEM-1K (NFR-003b): STX-framed 1024-byte data fields, else SOH/128.
        frame_size = 1024 if use_1k else 128
        start_byte = self.STX if use_1k else self.SOH

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
            # FR-120: a cancellation during the handshake aborts the transfer.
            if self._cancelled():
                self._abort()
            return False
        crc_mode = start == b"C"

        total = len(data)
        packet_num = 1  # X-Modem data packets are numbered from 1.
        blocks = 0
        bytes_done = 0
        offset = 0

        while offset < len(data):
            # FR-120: abort between packets when cancellation is requested.
            if self._cancelled():
                self._abort()
                return False

            # Create packet: start_byte + Seq + ~Seq + Data + trailer.
            # NFR-003c: the final short chunk is padded to a full data field
            # (128 or 1024 bytes) with the PAD byte before the trailer is
            # computed.
            chunk = data[offset : offset + frame_size]
            real_len = len(chunk)  # bytes from the file, before padding
            if real_len < frame_size:
                chunk = chunk + bytes([self.PAD]) * (frame_size - real_len)

            packet = (
                start_byte
                + bytes([packet_num])
                + bytes([255 - packet_num])
                + chunk
                + self._trailer(chunk, crc_mode)
            )

            # Send the packet, retransmitting the SAME packet on NAK/timeout.
            # The sequence number is fixed per packet and only advances on ACK.
            for _ in range(10):
                # FR-120: abort mid-retransmit when cancellation is requested.
                if self._cancelled():
                    self._abort()
                    return False
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

            offset += frame_size
            packet_num = (packet_num + 1) % 256

        # Send EOT, retransmitting until the receiver ACKs it (bounded).
        for _ in range(10):
            self._write(self.EOT)
            if self._wait_for_one_of((self.ACK,), timeout=2.0) == self.ACK:
                break
        return True

    def receive_file(self, save_path: str, use_1k: bool = False) -> bool:
        """Receives a file from Remote to Host (e.g. from CP/M PCPUT).

        X-Modem is receiver-driven and the receiver's start character selects
        the mode. The CP/M-side senders (PCPUT V1.0) speak **checksum** X-Modem
        and do not understand the CRC start character 'C' — sending it makes
        them abort with "Unknown response from host" — so by default we poll
        with NAK (checksum) first and only fall back to 'C' (CRC) if the sender
        does not answer NAK at all (NFR-003f; "checksum mode, not CRC").

        XMODEM-1K, however, is a CRC protocol: a 1K-capable sender only switches
        to 1024-byte STX frames once the receiver requests CRC mode with 'C'. So
        when ``use_1k`` is set we poll 'C' **first** (falling back to NAK), which
        is what coaxes the sender into 1K blocks. Either way SOH frames carry
        128 data bytes and STX frames carry 1024, so both sizes are accepted.

        Satisfies: FR-081, FR-082, FR-083, FR-105, FR-120, NFR-003f, NFR-003g,
            NFR-003h, NFR-003j, NFR-003k, NFR-003l.
        """
        received_data = bytearray()
        expected_packet = 1
        blocks = 0  # FR-105: count of accepted data packets, for progress

        # Drop any stale bytes (e.g. a CAN left from a previous aborted run)
        # so the first frame byte we read is genuinely the start of a packet.
        self.ser.reset_input_buffer()

        # 1. Establish the connection and the trailer mode by waiting for the
        #    first frame byte (SOH/STX data, or EOT for an empty transfer).
        #    For 1K we poll 'C' (CRC) first so 1K-capable senders use 1024-byte
        #    STX frames; otherwise NAK (checksum) is tried first because the
        #    CP/M senders are checksum-only and abort on a stray 'C'.
        char = b""
        crc_mode = False
        prompts = ((b"C", True), (self.NAK, False)) if use_1k else ((self.NAK, False), (b"C", True))
        for prompt, is_crc in prompts:
            for _ in range(6):
                # FR-120: a cancellation during the handshake aborts the receive.
                if self._cancelled():
                    self._abort()
                    return False
                self._write(prompt)
                char = self._read_byte(timeout=3.0)
                if char in (self.SOH, self.STX, self.EOT):
                    crc_mode = is_crc
                    break
            if char in (self.SOH, self.STX, self.EOT):
                break
        else:
            return False

        # A sender that goes SILENT after the last packet — e.g. its EOT was
        # lost or garbled on the wire, with every data byte already received —
        # must not hang the receive forever. Bound the consecutive read
        # *timeouts* (b"") so that once the budget is spent the receive finishes
        # with the data it has rather than NAKing into the void indefinitely.
        # Only silence counts: any byte that arrives (a frame, EOT, or even a
        # stray byte) proves the sender is still transmitting, so the budget is
        # reset and we keep NAKing to resync — never abandoning a live transfer
        # part-way, which would truncate it (a real risk on 1K, where a single
        # lost frame-start byte turns a 1024-byte payload into stray bytes).
        silent = 0
        max_silent = 5
        while True:
            # FR-120: abort the receive (and discard the partial file) on cancel.
            if self._cancelled():
                self._abort()
                return False

            if char == b"":
                # Read timed out: the sender produced nothing. After the last
                # packet this is a lost EOT with all data already received (the
                # CP/M sender has exited); bound the silent retries so it cannot
                # hang forever, then finish with the data (or fail if none came).
                silent += 1
                if silent > max_silent:
                    if not received_data:
                        return False
                    break
                self._write(self.NAK)
                char = self._read_byte(timeout=3.0)
                continue

            silent = 0  # a byte arrived — the sender is alive; reset the budget

            if char == self.EOT:
                self._write(self.ACK)
                break

            if char not in (self.SOH, self.STX):
                # A stray byte (e.g. a lost frame-start). NAK and resync on the
                # next frame; the sender is transmitting, so do not give up.
                self._write(self.NAK)
                char = self._read_byte(timeout=10.0)
                continue

            # Read the rest of the frame: Seq + ~Seq + data + trailer. SOH
            # frames hold 128 data bytes, STX frames hold 1024 (XMODEM-1K).
            # _read_exact reassembles each field in full even when the port's
            # short read timeout would otherwise slice a large 1K payload across
            # several reads and desynchronise the stream.
            size = 128 if char == self.SOH else 1024
            header = self._read_exact(2)
            payload = self._read_exact(size)
            trailer = self._read_exact(2 if crc_mode else 1)

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
