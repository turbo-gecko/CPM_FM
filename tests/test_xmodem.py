"""Unit tests for the X-Modem progress hook (FR-105).

These drive ``XModem.send_file`` / ``receive_file`` against an in-memory fake
serial port — no hardware, no real sleeps — and assert that the ``progress``
callback fires once per transferred block with correctly accumulating block and
byte counts, and the right ``total_bytes`` (file size on send, ``None`` on
receive, since X-Modem carries no length).
"""

from cpm_fm.terminal.xmodem import XModem

ACK = b"\x06"
SOH = b"\x01"
STX = b"\x02"  # 1K frame marker (XMODEM-1K)
EOT = b"\x04"
NAK = b"\x15"
CAN = b"\x18"


class _FakeSerial:
    """Minimal in-memory serial: reads pop from a pre-seeded byte queue,
    writes are captured. ``reset_input_buffer`` is a no-op so seeded receive
    data is not discarded by ``receive_file``'s initial flush (in a real port
    the bytes would arrive from the remote after the flush)."""

    def __init__(self, to_read: bytes = b""):
        self._inbuf = bytearray(to_read)
        self.written = bytearray()
        # FR-120: bookkeeping so tests can assert the cancel path flushes the
        # port in both directions.
        self.input_resets = 0
        self.output_resets = 0
        self.flushes = 0

    @property
    def in_waiting(self) -> int:
        return len(self._inbuf)

    def read(self, n: int = 1) -> bytes:
        chunk = bytes(self._inbuf[:n])
        del self._inbuf[:n]
        return chunk

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def reset_input_buffer(self) -> None:
        self.input_resets += 1

    def reset_output_buffer(self) -> None:
        self.output_resets += 1

    def flush(self) -> None:
        self.flushes += 1


def test_send_file_reports_progress_per_packet(tmp_path):
    # 300 bytes -> three 128-byte packets (128, 128, 44 real bytes).
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(256)) + bytes(44))  # 300 bytes

    # Receiver answers: 'C' (request CRC mode) then one ACK per packet + EOT ACK.
    fake = _FakeSerial(b"C" + ACK * 4)
    calls: list[tuple[int, int, int | None]] = []
    xm = XModem(fake, progress=lambda b, n, t: calls.append((b, n, t)))

    assert xm.send_file(str(path)) is True
    # One callback per data packet (not for the EOT), cumulative byte counts,
    # total_bytes == file size throughout.
    assert calls == [(1, 128, 300), (2, 256, 300), (3, 300, 300)]


def test_send_file_1k_uses_stx_1024_byte_frames(tmp_path):
    # NFR-003/UIR-089: with use_1k, host->remote sends use 1024-byte STX frames.
    # 1100 bytes -> two 1024-byte packets (1024 real, 76 real + 948 pad).
    path = tmp_path / "UP1K.TXT"
    path.write_bytes(bytes(range(256)) * 4 + bytes(76))  # 1100 bytes

    # Receiver requests CRC ('C'), then one ACK per packet + EOT ACK.
    fake = _FakeSerial(b"C" + ACK * 3)
    calls: list[tuple[int, int, int | None]] = []
    xm = XModem(fake, progress=lambda b, n, t: calls.append((b, n, t)))

    assert xm.send_file(str(path), use_1k=True) is True
    # Progress counts real file bytes; total is the 1100-byte file size.
    assert calls == [(1, 1024, 1100), (2, 1100, 1100)]
    # Frames are STX-led 1K packets (1 STX + 2 seq + 1024 data + 2 CRC = 1029),
    # never the 128-byte SOH form.
    assert xm.STX in fake.written
    assert fake.written[:1] == STX
    first_frame = fake.written[: 1 + 2 + 1024 + 2]
    assert len(first_frame) == 1029


def _checksum_packet(helper: XModem, seq: int, payload: bytes) -> bytes:
    # A checksum-mode SOH packet: SOH + seq + ~seq + 128 data + 1-byte checksum.
    chk = helper._calculate_checksum(payload)
    return SOH + bytes([seq, 255 - seq]) + payload + bytes([chk])


def test_receive_file_reports_progress_with_unknown_total(tmp_path):
    save = tmp_path / "DOWN.TXT"

    # Build two valid checksum-mode SOH packets (the mode the CP/M senders use).
    helper = XModem(_FakeSerial())
    p1 = bytes(range(128))
    p2 = bytes([0xAA]) * 128

    fake = _FakeSerial(_checksum_packet(helper, 1, p1) + _checksum_packet(helper, 2, p2) + EOT)
    calls: list[tuple[int, int, int | None]] = []
    xm = XModem(fake, progress=lambda b, n, t: calls.append((b, n, t)))

    assert xm.receive_file(str(save)) is True
    # One callback per accepted packet; total is None (length not carried).
    assert calls == [(1, 128, None), (2, 256, None)]
    assert save.read_bytes() == p1 + p2


def test_receive_file_polls_checksum_not_crc_first(tmp_path):
    # Regression: the CP/M senders (PCPUT V1.0) are checksum-only and abort on a
    # stray 'C' ("Unknown response from host"). The receiver must lead with NAK,
    # never 'C'. Seed one checksum packet so the handshake locks checksum mode.
    save = tmp_path / "DOWN.TXT"
    helper = XModem(_FakeSerial())
    payload = bytes(range(128))
    fake = _FakeSerial(_checksum_packet(helper, 1, payload) + EOT)
    xm = XModem(fake)

    assert xm.receive_file(str(save)) is True
    assert b"C" not in fake.written  # never poll with the CRC start character
    assert fake.written[:1] == NAK  # first poll is checksum (NAK)
    assert save.read_bytes() == payload


def test_send_file_cancel_aborts_and_sends_can(tmp_path):
    # FR-120: a cancellation request aborts the send, returns False, and emits
    # the CAN sequence so the remote receiver aborts too.
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(128)))
    # The receiver would otherwise proceed (seeded 'C' + ACKs), but cancellation
    # is requested before the handshake completes.
    fake = _FakeSerial(b"C" + ACK * 4)
    xm = XModem(fake, cancel_check=lambda: True)

    assert xm.send_file(str(path)) is False
    assert CAN in fake.written


def test_receive_file_cancel_aborts_and_sends_can(tmp_path):
    # FR-120: a cancellation request aborts the receive, returns False, sends
    # CAN, and writes no (partial) file.
    save = tmp_path / "DOWN.TXT"
    fake = _FakeSerial(b"")
    xm = XModem(fake, cancel_check=lambda: True)

    assert xm.receive_file(str(save)) is False
    assert CAN in fake.written
    assert not save.exists()


def test_cancel_flushes_serial_in_both_directions(tmp_path):
    # FR-120: aborting flushes the transmit and receive buffers so the in-flight
    # packet stops draining to the remote and stale incoming bytes are dropped,
    # rather than the transfer appearing to continue until the buffers empty.
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(128)))
    fake = _FakeSerial(b"C" + ACK * 4)
    xm = XModem(fake, cancel_check=lambda: True)

    assert xm.send_file(str(path)) is False
    # Output buffer discarded, then CAN flushed out, then input buffer discarded.
    assert fake.output_resets >= 1
    assert fake.input_resets >= 1
    assert fake.flushes >= 1


# --------------------------------------------------------------------------- #
# Independent integrity-math vectors (NFR-003).
#
# The progress tests above build each packet with the SAME _calculate_checksum
# / _crc16 the receiver then validates with, so a wrong checksum/CRC is
# invisible to them (a mutated _calculate_checksum left every progress test
# green). These tests pin the math against hand-computed, implementation-
# independent constants so a checksum/CRC fault cannot pass unnoticed.
# 0x31C3 is the canonical CRC-16/XMODEM check value for b"123456789".
# --------------------------------------------------------------------------- #


def test_calculate_checksum_matches_independent_vector():
    # NFR-003: checksum is (sum of bytes) mod 256, verified against fixed values.
    xm = XModem(_FakeSerial())
    assert xm._calculate_checksum(b"123456789") == 0xDD  # 477 & 0xFF
    assert xm._calculate_checksum(bytes(128)) == 0x00
    assert xm._calculate_checksum(b"\xff\xff\xff\xff") == 0xFC  # 1020 & 0xFF


def test_crc16_matches_canonical_xmodem_vector():
    # NFR-003: CRC-16/XMODEM (poly 0x1021, init 0x0000) against known answers.
    xm = XModem(_FakeSerial())
    assert xm._crc16(b"123456789") == 0x31C3  # canonical check value
    assert xm._crc16(b"") == 0x0000
    assert xm._crc16(b"A") == 0x58E5


def test_trailer_ok_validates_checksum_independently():
    # NFR-003: a correct 1-byte checksum trailer passes; a wrong one fails.
    xm = XModem(_FakeSerial())
    assert xm._trailer_ok(b"123456789", bytes([0xDD]), crc_mode=False) is True
    assert xm._trailer_ok(b"123456789", bytes([0xDE]), crc_mode=False) is False
    assert xm._trailer_ok(b"123456789", b"", crc_mode=False) is False  # missing trailer


def test_trailer_ok_validates_crc_independently():
    # NFR-003: a correct 2-byte big-endian CRC trailer passes; a wrong one fails.
    xm = XModem(_FakeSerial())
    assert xm._trailer_ok(b"123456789", bytes([0x31, 0xC3]), crc_mode=True) is True
    assert xm._trailer_ok(b"123456789", bytes([0x31, 0xC4]), crc_mode=True) is False
    assert xm._trailer_ok(b"123456789", bytes([0x31]), crc_mode=True) is False  # short


# --------------------------------------------------------------------------- #
# send_file error and edge paths.
# --------------------------------------------------------------------------- #


def test_send_file_returns_false_when_file_missing(tmp_path):
    # FR-081: a non-existent source file fails fast and transmits nothing.
    fake = _FakeSerial(b"C" + ACK * 4)
    assert XModem(fake).send_file(str(tmp_path / "does_not_exist.bin")) is False
    assert fake.written == b""


def test_send_file_returns_false_when_no_start_char(tmp_path, monkeypatch):
    # FR-082: if the receiver never sends a start character the send aborts with
    # False (and, absent a cancel, sends no CAN). The 60s handshake wait is
    # replaced by a stubbed timeout so the test does not block.
    path = tmp_path / "UP.TXT"
    path.write_bytes(b"x" * 10)
    fake = _FakeSerial(b"")
    xm = XModem(fake)
    monkeypatch.setattr(xm, "_wait_for_one_of", lambda *a, **k: b"")
    assert xm.send_file(str(path)) is False
    assert CAN not in fake.written


def test_send_file_aborts_after_nak_exhaustion(tmp_path):
    # NFR-003: a packet that is NAK'd on all 10 retransmit attempts gives up and
    # returns False rather than looping forever.
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(128)))
    fake = _FakeSerial(b"C" + NAK * 10)  # CRC handshake, then nothing but NAKs
    assert XModem(fake).send_file(str(path)) is False


def test_send_file_pads_final_short_chunk_with_eof(tmp_path):
    # NFR-003: a final chunk shorter than 128 bytes is padded to a full data
    # field with the 0x1A (Ctrl-Z) EOF byte before the trailer is computed.
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(100)))  # one short packet: 100 real + 28 pad
    fake = _FakeSerial(b"C" + ACK * 2)  # CRC start, ACK the packet, ACK the EOT
    assert XModem(fake).send_file(str(path)) is True
    # Frame layout: SOH(1) seq(1) ~seq(1) data(128) crc(2) ... so data is [3:131].
    data_field = fake.written[3:131]
    assert data_field[:100] == bytes(range(100))
    assert data_field[100:] == b"\x1a" * 28


# --------------------------------------------------------------------------- #
# receive_file mode / framing / recovery edge paths.
# --------------------------------------------------------------------------- #


def _checksum_packet_1k(helper: XModem, seq: int, payload: bytes) -> bytes:
    # A checksum-mode STX (1024-byte) packet, for the XMODEM-1K sender variants.
    chk = helper._calculate_checksum(payload)
    return STX + bytes([seq, 255 - seq]) + payload + bytes([chk])


def _crc_packet(helper: XModem, seq: int, payload: bytes) -> bytes:
    # A CRC-mode SOH packet: 2-byte big-endian CRC trailer.
    crc = helper._crc16(payload)
    return SOH + bytes([seq, 255 - seq]) + payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


class _CrcReceiveSerial:
    """Fake whose seeded packets are withheld until the receiver polls with 'C'.

    The first six reads return a non-frame junk byte (consumed by the six NAK
    handshake attempts, fast — never the 3s timeout), so the receiver falls
    through checksum mode to CRC mode, at which point the real frames are armed.
    """

    def __init__(self, frames: bytes):
        self._junk = bytearray(b"\x07" * 6)
        self._frames = bytearray(frames)
        self._armed = False
        self.written = bytearray()

    @property
    def in_waiting(self) -> int:
        return len(self._frames) if self._armed else len(self._junk)

    def read(self, n: int = 1) -> bytes:
        buf = self._frames if self._armed else self._junk
        chunk = bytes(buf[:n])
        del buf[:n]
        return chunk

    def write(self, data: bytes) -> int:
        self.written += data
        if b"C" in data:
            self._armed = True
        return len(data)

    def reset_input_buffer(self) -> None:
        pass

    def reset_output_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass


def test_receive_file_falls_through_to_crc_mode(tmp_path):
    # NFR-003: when the sender ignores NAK (checksum) the receiver polls 'C' and
    # validates a 2-byte CRC trailer. (crc16 correctness is pinned independently
    # by test_crc16_matches_canonical_xmodem_vector.)
    save = tmp_path / "DOWN.TXT"
    helper = XModem(_FakeSerial())
    payload = bytes(range(128))
    fake = _CrcReceiveSerial(_crc_packet(helper, 1, payload) + EOT)
    xm = XModem(fake)
    assert xm.receive_file(str(save)) is True
    assert b"C" in fake.written  # fell through to the CRC poll
    assert save.read_bytes() == payload


def test_receive_file_accepts_1k_stx_frame(tmp_path):
    # NFR-003: STX frames carry 1024 data bytes (XMODEM-1K) and must be accepted.
    save = tmp_path / "DOWN.BIN"
    helper = XModem(_FakeSerial())
    payload = bytes([0x5A]) * 1024
    fake = _FakeSerial(_checksum_packet_1k(helper, 1, payload) + EOT)
    assert XModem(fake).receive_file(str(save)) is True
    assert save.read_bytes() == payload


def _crc_packet_1k(helper: XModem, seq: int, payload: bytes) -> bytes:
    # A CRC-mode STX (1024-byte) packet: 2-byte big-endian CRC trailer.
    crc = helper._crc16(payload)
    return STX + bytes([seq, 255 - seq]) + payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


class _ChunkedSerial:
    """Serves seeded bytes but returns at most ``cap`` bytes per ``read()`` call,
    mimicking the transport port's short (0.1s) read timeout slicing a large 1K
    frame across several reads. ``receive_file`` must reassemble the full frame
    rather than truncating it on the first short read."""

    def __init__(self, to_read: bytes, cap: int = 64):
        self._inbuf = bytearray(to_read)
        self._cap = cap
        self.written = bytearray()

    @property
    def in_waiting(self) -> int:
        return len(self._inbuf)

    def read(self, n: int = 1) -> bytes:
        k = min(n, self._cap, len(self._inbuf))
        chunk = bytes(self._inbuf[:k])
        del self._inbuf[:k]
        return chunk

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def reset_input_buffer(self) -> None:
        pass

    def reset_output_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass


def test_receive_file_1k_frame_split_across_short_reads(tmp_path):
    # Regression: the transport port's 0.1s read timeout means ser.read(1024)
    # returns only a fraction of a 1K frame, so the frame must be reassembled
    # across several reads. A single short read would truncate the payload and
    # desync the stream (premature EOT, short file). Here the fake returns at
    # most 64 bytes per read; the full 1024-byte payload must still arrive whole.
    save = tmp_path / "DOWN.BIN"
    helper = XModem(_FakeSerial())
    payload = bytes(range(256)) * 4  # 1024 distinct-ish bytes
    fake = _ChunkedSerial(_crc_packet_1k(helper, 1, payload) + EOT, cap=64)
    xm = XModem(fake)

    assert xm.receive_file(str(save), use_1k=True) is True
    assert save.read_bytes() == payload  # full 1024 bytes, nothing truncated


def test_receive_file_1k_polls_crc_first(tmp_path):
    # NFR-003/UIR-089: XMODEM-1K is a CRC protocol — with use_1k the receiver
    # must lead with 'C' (not NAK) so a 1K-capable sender switches to 1024-byte
    # STX frames. The default (checksum-first) path is pinned separately by
    # test_receive_file_polls_checksum_not_crc_first.
    save = tmp_path / "DOWN.BIN"
    helper = XModem(_FakeSerial())
    payload = bytes([0x5A]) * 1024
    fake = _FakeSerial(_crc_packet_1k(helper, 1, payload) + EOT)
    xm = XModem(fake)

    assert xm.receive_file(str(save), use_1k=True) is True
    assert fake.written[:1] == b"C"  # first poll is the CRC start character
    assert save.read_bytes() == payload


def test_receive_file_reacks_duplicate_packet_once(tmp_path):
    # NFR-003: a re-sent packet (lost ACK) is re-ACK'd but stored only once.
    save = tmp_path / "DOWN.TXT"
    helper = XModem(_FakeSerial())
    p1 = bytes(range(128))
    p2 = bytes([0xAA]) * 128
    stream = (
        _checksum_packet(helper, 1, p1)
        + _checksum_packet(helper, 1, p1)  # duplicate of packet 1
        + _checksum_packet(helper, 2, p2)
        + EOT
    )
    calls: list[tuple[int, int, int | None]] = []
    fake = _FakeSerial(stream)
    xm = XModem(fake, progress=lambda b, n, t: calls.append((b, n, t)))
    assert xm.receive_file(str(save)) is True
    assert save.read_bytes() == p1 + p2  # duplicate not appended twice
    assert calls == [(1, 128, None), (2, 256, None)]  # no progress for the dup


def test_receive_file_recovers_from_corrupt_trailer(tmp_path):
    # NFR-003: a packet with a bad trailer is NAK'd and the resent good copy is
    # accepted. Only the checksum byte is corrupted, isolating the trailer check.
    save = tmp_path / "DOWN.TXT"
    helper = XModem(_FakeSerial())
    payload = bytes(range(128))
    good = _checksum_packet(helper, 1, payload)
    corrupt = good[:-1] + bytes([good[-1] ^ 0xFF])
    fake = _FakeSerial(corrupt + good + EOT)
    assert XModem(fake).receive_file(str(save)) is True
    assert save.read_bytes() == payload
    # Receiver writes only control bytes: one handshake NAK + one rejecting the
    # corrupt packet == two NAKs total.
    assert fake.written.count(0x15) == 2


class _SilentTailSerial:
    """Serves seeded bytes, then returns b"" *immediately* to simulate a sender
    that has finished and gone quiet. ``in_waiting`` always reports readable so
    ``_read_byte`` never sleeps to a real timeout — once the buffer is exhausted
    every read is an instant empty "timeout", exercising the silent-retry bound
    without slow tests.
    """

    def __init__(self, to_read: bytes):
        self._inbuf = bytearray(to_read)
        self.written = bytearray()

    @property
    def in_waiting(self) -> int:
        return 1

    def read(self, n: int = 1) -> bytes:
        chunk = bytes(self._inbuf[:n])
        del self._inbuf[:n]
        return chunk

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def reset_input_buffer(self) -> None:
        pass

    def reset_output_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass


def test_receive_file_completes_when_eot_is_lost(tmp_path):
    # Regression: if the sender goes SILENT after the last packet (its EOT lost
    # or garbled) with every byte already received, the receive must finish with
    # the data after a bounded number of silent NAK retries rather than hang.
    save = tmp_path / "DOWN.TXT"
    helper = XModem(_FakeSerial())
    payload = bytes(range(128))
    fake = _SilentTailSerial(_checksum_packet(helper, 1, payload))  # no EOT
    xm = XModem(fake)

    assert xm.receive_file(str(save)) is True
    assert save.read_bytes() == payload  # the fully-received file is written


def test_receive_file_resyncs_after_stray_bytes_between_packets(tmp_path):
    # Regression: a burst of stray bytes mid-transfer (e.g. a lost frame-start
    # turning a 1K payload into noise) must NOT truncate the receive — while the
    # sender is still transmitting the receiver keeps NAKing and resyncs on the
    # next real frame. A bound that counted stray bytes (not just silence) would
    # wrongly give up here and write a short file.
    save = tmp_path / "DOWN.TXT"
    helper = XModem(_FakeSerial())
    p1 = bytes(range(128))
    p2 = bytes([0xAA]) * 128
    stream = (
        _checksum_packet(helper, 1, p1)
        + b"\x07" * 20  # stray noise, well over any stall budget
        + _checksum_packet(helper, 2, p2)
        + EOT
    )
    xm = XModem(_FakeSerial(stream))

    assert xm.receive_file(str(save)) is True
    assert save.read_bytes() == p1 + p2  # both packets present, nothing dropped


def test_receive_file_empty_transfer_writes_empty_file(tmp_path):
    # NFR-003: an immediate EOT (no data packets) is a valid, empty transfer.
    save = tmp_path / "EMPTY.TXT"
    fake = _FakeSerial(EOT)
    assert XModem(fake).receive_file(str(save)) is True
    assert save.read_bytes() == b""
    assert ACK in fake.written
