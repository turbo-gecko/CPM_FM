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
        pass


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
