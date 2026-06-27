"""Content-integrity helpers for the protocol tier (plan §2.3, §5).

``sample_files`` builds a representative set of files (short text, binary,
extensionless, and a multi-block file ≥1 KB). ``assert_round_trip`` does a
**block-aware** byte comparison: X-Modem/CP/M pads the final 128- or 1024-byte
frame with the EOF byte 0x1A (Ctrl-Z), so a downloaded file is the original
followed by 0x1A padding up to the next frame boundary. A naive ``==`` would
wrongly fail; we assert the leading bytes match exactly and the trailing bytes
are pure 0x1A padding.
"""

from __future__ import annotations

from pathlib import Path

PAD = 0x1A  # CP/M EOF / X-Modem final-frame padding (NFR-003c)


def sample_files(dst_dir: str | Path) -> list[Path]:
    """Create the representative sample files in ``dst_dir`` and return paths.

    All names conform to CP/M 8.3 so they upload without a rename prompt.
    Sizes are deliberately NOT frame multiples so the round-trip exercises the
    0x1A padding path.
    """
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)
    specs: list[tuple[str, bytes]] = [
        ("SHORT.TXT", b"Hello CP/M over X-Modem!\r\n"),
        # Binary across the full byte range; ends on a non-0x1A byte so the
        # padding boundary is unambiguous.
        ("BINARY.DAT", bytes(range(256)) + bytes(reversed(range(256))) + b"\x00\x55"),
        ("NOEXT", b"extensionless file body\r\n"),
        # Multi-block (>1 KB): spans several 128-byte frames / one 1K frame.
        ("BIG.DAT", bytes((i * 37 + 11) & 0xFF for i in range(3000)) + b"\x7e"),
    ]
    paths = []
    for name, data in specs:
        p = dst / name
        p.write_bytes(data)
        paths.append(p)
    return paths


def assert_round_trip(src: str | Path, dst: str | Path) -> None:
    """Assert ``dst`` is a faithful X-Modem round-trip of ``src``.

    The received file must begin with the original bytes exactly; any trailing
    bytes must be pure 0x1A frame padding, and the total length must round up to
    a 128-byte frame boundary.
    """
    src_bytes = Path(src).read_bytes()
    dst_bytes = Path(dst).read_bytes()
    n = len(src_bytes)
    assert dst_bytes[:n] == src_bytes, (
        f"payload mismatch for {Path(src).name}: {src_bytes[:32]!r} != {dst_bytes[:32]!r}"
    )
    tail = dst_bytes[n:]
    assert all(b == PAD for b in tail), (
        f"trailing bytes of {Path(dst).name} are not pure 0x1A padding: {tail[:32]!r}"
    )
    assert len(dst_bytes) % 128 == 0, (
        f"received length {len(dst_bytes)} is not a 128-byte frame multiple"
    )
