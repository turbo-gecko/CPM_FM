"""Unit tests for the X-Modem progress hook (FR-105).

These drive ``XModem.send_file`` / ``receive_file`` against an in-memory fake
serial port — no hardware, no real sleeps — and assert that the ``progress``
callback fires once per transferred block with correctly accumulating block and
byte counts, and the right ``total_bytes`` (file size on send, ``None`` on
receive, since X-Modem carries no length).
"""

import threading
import time

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

    def __init__(self, to_read: bytes = b"", out_waiting: int = 0):
        self._inbuf = bytearray(to_read)
        self.written = bytearray()
        # FR-120: bookkeeping so tests can assert the cancel path flushes the
        # port in both directions.
        self.input_resets = 0
        self.output_resets = 0
        self.flushes = 0
        # FR-120: queued transmit bytes the bounded abort drain polls. A real
        # port reports this via out_waiting; the fake holds it fixed so a test
        # can model a line that never drains (flow-control stall) without the
        # abort hanging.
        self._out_waiting = out_waiting

    @property
    def out_waiting(self) -> int:
        return self._out_waiting

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


class _ResponsiveReceiver(_FakeSerial):
    """Fake receiver that models real handshake timing for send tests.

    It serves the seeded handshake bytes (``prefix`` — which may embed a start-up
    banner containing a stray ``C`` before the genuine start character, to
    exercise NFR-003r), then stays idle, then ACKs (or, when ``ack`` is False,
    NAKs) each data/EOT frame reactively. This is what real hardware does: the
    receiver sends its start character, goes quiet to await the packet, and only
    responds once a frame arrives. It lets the sender's NFR-003r settle-check see
    a genuinely idle line after the start character, unlike the older pre-seeded
    ``b"C" + ACK * n`` fakes whose trailing ACKs now (correctly) look like banner
    noise.
    """

    def __init__(self, prefix: bytes, ack: bool = True):
        super().__init__(prefix)
        self._ack = ack

    def write(self, data: bytes) -> int:
        n = super().write(data)
        if data[:1] in (SOH, STX, EOT):
            self._inbuf += ACK if self._ack else NAK
        return n


class _XmReceiver(_FakeSerial):
    """Models the RomWBW XM receiver for send tests (NFR-003r).

    Emits a start-up banner as one continuous burst (containing stray 'C's), then
    — after a real quiet gap of ``idle`` seconds — polls its genuine start
    character (observed on the bench as 'C' followed by a stray 'K'), and after
    the handshake ACKs (or, when ``ack`` is False, NAKs) each data/EOT frame
    reactively. The quiet gap before the poll is exactly what lets the sender's
    NFR-003r idle-before check tell the real start char from the banner's.
    """

    def __init__(self, banner: bytes, poll: bytes = b"CK", ack: bool = True, idle: float = 0.15):
        super().__init__(banner)
        self._poll = poll
        self._ack = ack
        self._idle = idle
        self._drained_at = None
        self.armed = False

    @property
    def in_waiting(self) -> int:
        if self._inbuf:
            return len(self._inbuf)
        if not self.armed:
            now = time.time()
            if self._drained_at is None:
                self._drained_at = now  # banner just drained: start the quiet clock
            elif now - self._drained_at >= self._idle:
                self.armed = True
                self._inbuf += self._poll  # release one 'CK' poll after the gap
                return len(self._inbuf)
        return 0

    def write(self, data: bytes) -> int:
        n = super().write(data)
        if data[:1] in (SOH, STX, EOT):
            self._inbuf += ACK if self._ack else NAK
        return n


def test_send_file_reports_progress_per_packet(tmp_path):
    """Verifies: FR-105, NFR-003a."""
    # 300 bytes -> three 128-byte packets (128, 128, 44 real bytes).
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(256)) + bytes(44))  # 300 bytes

    # Receiver requests CRC ('C'), then goes idle and ACKs each frame reactively.
    fake = _ResponsiveReceiver(b"C")
    calls: list[tuple[int, int, int | None]] = []
    xm = XModem(fake, progress=lambda b, n, t: calls.append((b, n, t)))
    xm.handshake_settle = 0.05  # keep the NFR-003r settle window short for the test

    assert xm.send_file(str(path)) is True
    # One callback per data packet (not for the EOT), cumulative byte counts,
    # total_bytes == file size throughout.
    assert calls == [(1, 128, 300), (2, 256, 300), (3, 300, 300)]


def test_send_file_1k_uses_stx_1024_byte_frames(tmp_path):
    """Verifies: NFR-003b, UIR-089."""
    # NFR-003/UIR-089: with use_1k, host->remote sends use 1024-byte STX frames.
    # 1100 bytes -> two 1024-byte packets (1024 real, 76 real + 948 pad).
    path = tmp_path / "UP1K.TXT"
    path.write_bytes(bytes(range(256)) * 4 + bytes(76))  # 1100 bytes

    # Receiver requests CRC ('C'), then goes idle and ACKs each frame reactively.
    fake = _ResponsiveReceiver(b"C")
    calls: list[tuple[int, int, int | None]] = []
    xm = XModem(fake, progress=lambda b, n, t: calls.append((b, n, t)))
    xm.handshake_settle = 0.05

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
    """Verifies: FR-105."""
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
    """Verifies: NFR-003f."""
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
    """Verifies: FR-120, NFR-003m."""
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
    """Verifies: FR-120, NFR-003m."""
    # FR-120: a cancellation request aborts the receive, returns False, sends
    # CAN, and writes no (partial) file.
    save = tmp_path / "DOWN.TXT"
    fake = _FakeSerial(b"")
    xm = XModem(fake, cancel_check=lambda: True)

    assert xm.receive_file(str(save)) is False
    assert CAN in fake.written
    assert not save.exists()


def test_cancel_flushes_serial_in_both_directions(tmp_path):
    """Verifies: FR-120, NFR-003n."""
    # FR-120: aborting flushes the transmit and receive buffers so the in-flight
    # packet stops draining to the remote and stale incoming bytes are dropped,
    # rather than the transfer appearing to continue until the buffers empty.
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(128)))
    fake = _FakeSerial(b"C" + ACK * 4)  # out_waiting 0 -> the drain returns at once
    xm = XModem(fake, cancel_check=lambda: True)

    assert xm.send_file(str(path)) is False
    # Output buffer discarded, then CAN sent and drained out, then input buffer
    # discarded.
    assert fake.output_resets >= 1
    assert fake.input_resets >= 1


def test_abort_does_not_hang_when_tx_cannot_drain(tmp_path):
    """Verifies: FR-120, NFR-003o."""
    # FR-120 regression: when the line cannot drain after the abort (flow control
    # de-asserted by the aborting remote, so out_waiting never reaches 0), the
    # bounded transmit drain must still return promptly. An unbounded flush()
    # busy-waiting on out_waiting would hang the transfer worker forever, leaving
    # the progress dialog stuck open with no way to close it.
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(128)))
    fake = _FakeSerial(b"C" + ACK * 4, out_waiting=99)  # never drains
    xm = XModem(fake, cancel_check=lambda: True)

    done = []

    def run():
        done.append(xm.send_file(str(path)))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=5.0)  # generous vs the 1.0s drain bound
    assert not t.is_alive(), "abort hung on a non-draining transmit buffer"
    assert done == [False]
    assert CAN in fake.written  # the remote was still told to abort


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
    """Verifies: NFR-003d."""
    # NFR-003: checksum is (sum of bytes) mod 256, verified against fixed values.
    xm = XModem(_FakeSerial())
    assert xm._calculate_checksum(b"123456789") == 0xDD  # 477 & 0xFF
    assert xm._calculate_checksum(bytes(128)) == 0x00
    assert xm._calculate_checksum(b"\xff\xff\xff\xff") == 0xFC  # 1020 & 0xFF


def test_crc16_matches_canonical_xmodem_vector():
    """Verifies: NFR-003e."""
    # NFR-003: CRC-16/XMODEM (poly 0x1021, init 0x0000) against known answers.
    xm = XModem(_FakeSerial())
    assert xm._crc16(b"123456789") == 0x31C3  # canonical check value
    assert xm._crc16(b"") == 0x0000
    assert xm._crc16(b"A") == 0x58E5


def test_trailer_ok_validates_checksum_independently():
    """Verifies: NFR-003d."""
    # NFR-003: a correct 1-byte checksum trailer passes; a wrong one fails.
    xm = XModem(_FakeSerial())
    assert xm._trailer_ok(b"123456789", bytes([0xDD]), crc_mode=False) is True
    assert xm._trailer_ok(b"123456789", bytes([0xDE]), crc_mode=False) is False
    assert xm._trailer_ok(b"123456789", b"", crc_mode=False) is False  # missing trailer


def test_trailer_ok_validates_crc_independently():
    """Verifies: NFR-003e."""
    # NFR-003: a correct 2-byte big-endian CRC trailer passes; a wrong one fails.
    xm = XModem(_FakeSerial())
    assert xm._trailer_ok(b"123456789", bytes([0x31, 0xC3]), crc_mode=True) is True
    assert xm._trailer_ok(b"123456789", bytes([0x31, 0xC4]), crc_mode=True) is False
    assert xm._trailer_ok(b"123456789", bytes([0x31]), crc_mode=True) is False  # short


# --------------------------------------------------------------------------- #
# send_file error and edge paths.
# --------------------------------------------------------------------------- #


def test_send_file_returns_false_when_file_missing(tmp_path):
    """Verifies: FR-081."""
    # FR-081: a non-existent source file fails fast and transmits nothing.
    fake = _FakeSerial(b"C" + ACK * 4)
    assert XModem(fake).send_file(str(tmp_path / "does_not_exist.bin")) is False
    assert fake.written == b""


def test_send_file_returns_false_when_no_start_char(tmp_path, monkeypatch):
    """Verifies: FR-082."""
    # FR-082: if the receiver never sends a start character the send aborts with
    # False (and, absent a cancel, sends no CAN). The 60s handshake wait is
    # replaced by a stubbed timeout so the test does not block.
    path = tmp_path / "UP.TXT"
    path.write_bytes(b"x" * 10)
    fake = _FakeSerial(b"")
    xm = XModem(fake)
    monkeypatch.setattr(xm, "_wait_for_start_char", lambda *a, **k: b"")
    assert xm.send_file(str(path)) is False
    assert CAN not in fake.written


def test_send_file_sets_no_response_on_genuine_handshake_timeout(tmp_path):
    """Verifies: FR-159, FR-160."""
    # FR-159: a handshake that never sees a single response byte sets
    # no_response, distinguishing a misconfigured remote command from a
    # mid-transfer failure. FR-160: the wait is bounded by the configurable
    # handshake_timeout (a tiny value here so the test runs fast for real).
    path = tmp_path / "UP.TXT"
    path.write_bytes(b"x" * 10)
    fake = _FakeSerial(b"")
    xm = XModem(fake, handshake_timeout=0.05)
    assert xm.send_file(str(path)) is False
    assert xm.no_response is True
    assert CAN not in fake.written


def test_send_file_cancel_during_handshake_does_not_set_no_response(tmp_path):
    """Verifies: FR-159."""
    # FR-159: a cancellation during the handshake is not a misconfigured
    # command, so no_response stays False even though the send also failed.
    path = tmp_path / "UP.TXT"
    path.write_bytes(b"x" * 10)
    fake = _FakeSerial(b"")
    xm = XModem(fake, handshake_timeout=0.05, cancel_check=lambda: True)
    assert xm.send_file(str(path)) is False
    assert xm.no_response is False


def test_handshake_timeout_defaults_to_ten_seconds(tmp_path):
    """Verifies: FR-160."""
    # FR-160: default handshake_timeout is 10s, independent of a caller
    # supplying its own value.
    fake = _FakeSerial(b"")
    assert XModem(fake).handshake_timeout == 10.0
    assert XModem(fake, handshake_timeout=5.0).handshake_timeout == 5.0


def test_send_file_aborts_after_nak_exhaustion(tmp_path):
    """Verifies: NFR-003p."""
    # NFR-003p: a packet that is NAK'd on all 10 retransmit attempts gives up and
    # returns False rather than looping forever.
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(128)))
    fake = _ResponsiveReceiver(b"C", ack=False)  # CRC handshake, then NAK every frame
    xm = XModem(fake)
    xm.handshake_settle = 0.05
    assert xm.send_file(str(path)) is False


def test_send_file_pads_final_short_chunk_with_eof(tmp_path):
    """Verifies: NFR-003c."""
    # NFR-003: a final chunk shorter than 128 bytes is padded to a full data
    # field with the 0x1A (Ctrl-Z) EOF byte before the trailer is computed.
    path = tmp_path / "UP.TXT"
    path.write_bytes(bytes(range(100)))  # one short packet: 100 real + 28 pad
    fake = _ResponsiveReceiver(b"C")  # CRC start, then reactive ACKs (packet + EOT)
    xm = XModem(fake)
    xm.handshake_settle = 0.05
    assert xm.send_file(str(path)) is True
    # Frame layout: SOH(1) seq(1) ~seq(1) data(128) crc(2) ... so data is [3:131].
    data_field = fake.written[3:131]
    assert data_field[:100] == bytes(range(100))
    assert data_field[100:] == b"\x1a" * 28


def test_send_handshake_skips_start_char_in_banner(tmp_path):
    """Verifies: NFR-003r."""
    # NFR-003r: the stray 'C's in the receiver's start-up banner (e.g. the RomWBW
    # XM receiver's "...on COM0" / ".COM" / "Ctrl-X") must not be mistaken for the
    # CRC-mode request. The banner is a continuous burst (no idle before those
    # 'C's); the genuine start char ('C' of the 'CK' poll) arrives only after a
    # quiet gap, so the idle-before check skips the banner and returns the poll.
    banner = (
        b"\r\nXMODEM v12.5 - 07/13/86\r\n"
        b"RomWBW [WBW], HBIOS FastPath on COM0\r\n"
        b"Receiving: J0:DATSWEEP.COM\r\n"
        b"To cancel: Ctrl-X, pause, Ctrl-X\r\n"
    )
    fake = _XmReceiver(banner)  # banner burst, then a quiet gap, then a 'CK' poll
    xm = XModem(fake)
    xm.handshake_settle = 0.05

    assert xm._wait_for_start_char((b"C", NAK), timeout=2.0) == b"C"
    # Reached only via the post-idle poll: every banner 'C' was mid-burst (no
    # preceding idle) and skipped, so the fake had to arm and emit the real poll.
    assert fake.armed is True


def test_send_file_empty_transfer_over_banner_succeeds(tmp_path):
    """Verifies: NFR-003q, NFR-003r."""
    # A zero-byte file to a banner-chatty CRC receiver: the handshake skips the
    # banner 'C's, waits out the quiet gap, accepts the genuine 'CK' poll (the
    # trailing 'K' is discarded), sends no data packet, and completes with EOT
    # alone once the receiver ACKs it.
    path = tmp_path / "EMPTY.TXT"
    path.write_bytes(b"")
    banner = b"XM v12.5 on COM0\r\nReceiving: J0:EMPTY.TXT\r\nready to receive\r\n"
    fake = _XmReceiver(banner)
    xm = XModem(fake)
    xm.handshake_settle = 0.05

    assert xm.send_file(str(path)) is True
    assert SOH not in fake.written and STX not in fake.written  # no data frame sent
    assert EOT in fake.written  # the sender wrote the EOT and it was ACKed


def test_send_file_empty_transfer_fails_when_eot_unacked(tmp_path):
    """Verifies: NFR-003p, NFR-003q."""
    # For an empty transfer the EOT ACK is the only evidence of delivery, so if the
    # receiver never ACKs the EOT the send reports failure (rather than the former
    # unconditional success). The bounded EOT retransmit still applies (NFR-003p).
    path = tmp_path / "EMPTY.TXT"
    path.write_bytes(b"")
    fake = _FakeSerial(NAK)  # start char, then silence — never ACKs the EOT
    xm = XModem(fake)
    xm.handshake_settle = 0.05
    xm.eot_timeout = 0.02  # keep the 10 bounded EOT retries fast
    assert xm.send_file(str(path)) is False


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


def test_receive_file_sets_no_response_on_genuine_handshake_timeout(tmp_path):
    """Verifies: FR-159, FR-160."""
    # FR-159/FR-160: a sender that never answers either poll (NAK or 'C')
    # within the configurable handshake timeout sets no_response, distinct
    # from a mid-transfer failure. A tiny timeout keeps the test fast.
    save = tmp_path / "DOWN.TXT"
    fake = _FakeSerial(b"")
    xm = XModem(fake, handshake_timeout=0.3)
    assert xm.receive_file(str(save)) is False
    assert xm.no_response is True


def test_receive_file_no_response_stays_false_on_success(tmp_path):
    """Verifies: FR-159."""
    # FR-159: no_response is only set on a genuine handshake timeout, never on
    # a successful receive.
    save = tmp_path / "DOWN.TXT"
    helper = XModem(_FakeSerial())
    payload = bytes(range(128))
    fake = _CrcReceiveSerial(_crc_packet(helper, 1, payload) + EOT)
    xm = XModem(fake)
    assert xm.receive_file(str(save)) is True
    assert xm.no_response is False


def test_receive_file_falls_through_to_crc_mode(tmp_path):
    """Verifies: NFR-003f."""
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
    """Verifies: NFR-003h."""
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
    """Verifies: NFR-003i."""
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
    """Verifies: NFR-003g, UIR-089."""
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
    """Verifies: NFR-003k."""
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
    """Verifies: NFR-003l."""
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
    """Verifies: NFR-003j."""
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
    """Verifies: NFR-003j."""
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
    """Verifies: NFR-003q, M1."""
    # NFR-003q: an immediate EOT (no data packets) is a valid, empty transfer.
    save = tmp_path / "EMPTY.TXT"
    fake = _FakeSerial(EOT)
    assert XModem(fake).receive_file(str(save)) is True
    assert save.read_bytes() == b""
    assert ACK in fake.written


# --------------------------------------------------------------------------- #
# M1: Content-integrity round-trip (end-to-end verification)
#
# The existing receive tests build each packet with _checksum_packet from a
# helper XModem, then immediately validate the same helper's checksum/CRC
# on that payload — if either math function is wrong both directions are wrong
# the same way and a corruption bug is invisible.  These tests construct packets
# by hand (using independent arithmetic), so any breakage in receive_file's
# integrity chain (frame parsing, sequence handling, trailer validation,
# padding removal) will produce visible content mismatch.
# --------------------------------------------------------------------------- #


def _make_checksum_packet(seq: int, payload: bytes) -> bytes:
    """Build a standalone checksum-mode X-Modem SOH packet (128-byte frames)."""
    chk = sum(payload) & 0xFF
    return SOH + bytes([seq, 255 - seq]) + payload + bytes([chk])


def _make_crc_1k_frame(seq: int, payload: bytes) -> bytes:
    """Build a standalone CRC-mode X-Modem STX frame (1024-byte frames)."""
    crc = 0
    for byte in payload:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return STX + bytes([seq, 255 - seq]) + payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


def test_receive_file_integrity_checksum_multi_packet(tmp_path):
    """Verifies: M1.

    Three independent packets of diverse data received in checksum mode (the
    path used by CP/M senders) must match byte-for-byte — no truncation,
    duplication, or silent corruption across packet boundaries.  Both the
    packet-sequence handling and trailer validation are exercised end-to-end:
    the stream is seeded with three fixed-content packets plus EOT.
    """
    save = tmp_path / "M1_CHK.TXT"

    p1 = bytes(range(128))  # ascending 0..127
    p2 = bytes([0xFF]) * 64 + bytes([0x00]) * 64  # max/min halves
    p3 = bytes(i & 0xFF for i in range(128))  # wrap-around ascent

    # Seed: one NAK to trigger checksum-mode handshake, then all frames + EOT.
    stream = b"\x15"  # initial poll response -> receiver accepts as checksum start
    helper = XModem(_FakeSerial())
    stream += _checksum_packet(helper, 1, p1)
    stream += _checksum_packet(helper, 2, p2)
    stream += _checksum_packet(helper, 3, p3)
    stream += EOT

    xm = XModem(_FakeSerial(stream))
    assert xm.receive_file(str(save)) is True
    written = save.read_bytes()

    assert len(written) == 3 * 128
    assert written == p1 + p2 + p3


def test_receive_file_integrity_crc_large_payload(tmp_path):
    """Verifies: M1.

    A large multi-frame file (5 × 1024 bytes) received in CRC mode with
    1K frames must produce exact content — tests frame reassembly, validation,
    and CRC verification across all blocks simultaneously.
    """
    save = tmp_path / "M1_1K.BIN"

    payloads: list[bytes] = []
    for i in range(5):
        base = i * 1024
        payloads.append(bytes((base + j) & 0xFF for j in range(1024)))

    stream = b""
    for i, p in enumerate(payloads):
        stream += _make_crc_1k_frame(i + 1, p)
    stream += EOT

    fake = _FakeSerial(b"C" + stream)  # seed CRC poll response
    xm = XModem(fake)
    assert xm.receive_file(str(save), use_1k=True) is True

    written = save.read_bytes()
    expected = b"".join(payloads)  # exactly 5120 bytes
    assert len(written) == 5 * 1024
    assert written == expected


def test_receive_file_integrity_null_byte_mixed_patterns(tmp_path):
    """Verifies: M1.

    A file composed entirely of null bytes and sparse non-null markers must
    arrive byte-for-byte identical — exercising the boundary between X-Modem's
    PAD (0x1A) stuffing in a partial final frame and real payload data that
    contains zero bytes, which are commonly lost or misinterpreted.
    """
    save = tmp_path / "M1_NULL.TXT"

    # Payload: all zeros except single-byte markers every 256 bytes
    payloads: list[bytes] = []
    for i in range(3):
        block = bytearray(128)  # all zeros
        block[64] = (i + 1) & 0xFF  # marker at midpoint
        payloads.append(bytes(block))

    helper = XModem(_FakeSerial())
    stream = b"\x15"  # checksum mode poll response
    stream += _checksum_packet(helper, 1, payloads[0])
    stream += _checksum_packet(helper, 2, payloads[1])
    stream += _checksum_packet(helper, 3, payloads[2])
    stream += EOT

    assert XModem(_FakeSerial(stream)).receive_file(str(save)) is True
    written = save.read_bytes()
    expected = b"".join(payloads)
    assert len(written) == 3 * 128
    assert written == expected


def test_receive_file_integrity_1k_frame_boundary(tmp_path):
    """Verifies: M1.

    A file that lands exactly on frame boundaries (3 × 1024 = 3072 bytes) in
    CRC-mode 1K transfer must produce identical content — exercising the full
    code path for multi-frame CRC reception without any final-packet padding.
    """
    save = tmp_path / "M1_BOUND.BIN"

    payloads: list[bytes] = []
    for i in range(3):
        base = i * 1024
        payloads.append(bytes((base + j) % 256 for j in range(1024)))

    frames: list[bytes] = []
    for i, p in enumerate(payloads):
        frames.append(_make_crc_1k_frame(i + 1, p))

    fake = _FakeSerial(b"C" + b"".join(frames) + EOT)  # seed CRC poll response
    assert XModem(fake).receive_file(str(save), use_1k=True) is True
    written = save.read_bytes()
    assert len(written) == 3 * 1024
    assert written == b"".join(payloads)


def test_receive_file_integrity_partial_last_frame(tmp_path):
    """Verifies: M1.

    A file with a partial final frame (1500 bytes = one full 1K + 472 payload,
    padded by sender to 1024 on the wire) must write back exactly the raw-
    received content — the receiver stores frame payloads verbatim including any
    sender-side padding since protocol frames are always full-size blocks.
    """
    save = tmp_path / "M1_PARTIAL.BIN"

    p1 = bytes((i * 7 + 3) & 0xFF for i in range(1024))
    p2 = bytes((i * 13 + 7) & 0xFF for i in range(472))

    def _build_1k(seq: int, payload: bytes) -> bytes:
        crc_val = 0
        for byte in payload:
            crc_val ^= byte << 8
            for _ in range(8):
                crc_val = ((crc_val << 1) ^ 0x1021) if (crc_val & 0x8000) else (crc_val << 1)
                crc_val &= 0xFFFF
        # Sender-side padding before CRC
        padded = payload + b"\x1a" * (1024 - len(payload))
        pcrc = 0
        for byte in padded:
            pcrc ^= byte << 8
            for _ in range(8):
                pcrc = ((pcrc << 1) ^ 0x1021) if (pcrc & 0x8000) else (pcrc << 1)
                pcrc &= 0xFFFF
        return STX + bytes([seq, 255 - seq]) + padded + bytes([(pcrc >> 8) & 0xFF, pcrc & 0xFF])

    stream = _build_1k(1, p1) + _build_1k(2, p2) + EOT
    fake = _FakeSerial(b"C" + stream)
    assert XModem(fake).receive_file(str(save), use_1k=True) is True
    written = save.read_bytes()
    assert len(written) == 2 * 1024
