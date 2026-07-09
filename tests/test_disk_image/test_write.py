"""Tests for the CP/M image write path: encode → save → re-open round-trips.

The writer is validated against the reader (a write→save→re-open cycle must
preserve every file's name, user, attributes and byte content) and against the
independent synthetic builder in ``conftest`` — both must decode to the same
files. Capacity and filename failures must raise typed errors and write nothing.

Verifies: FR-174, DR-050.
"""

from __future__ import annotations

import pytest

from cpm_fm.utils.disk_image import load_diskdefs
from cpm_fm.utils.disk_image.filesystem import (
    DirectoryFullError,
    DiskFullError,
    InvalidNameError,
    split_83,
)
from cpm_fm.utils.disk_image.image import CpmImage


def _geom(name):
    d = load_diskdefs().get(name)
    assert d is not None
    return d


def _blank(geom):
    """A freshly formatted (empty directory) image for ``geom``."""
    return bytearray([0xE5]) * geom.total_bytes


def _roundtrip(geom, files, tmp_path, *, attrs=None):
    """Write ``files`` into a blank image, save, re-open, and return the reopened image."""
    attrs = attrs or {}
    img = CpmImage(_blank(geom), geom)
    for name, data in files.items():
        ro, sys_, arc = attrs.get(name, (False, False, False))
        img.write_file(name, data, read_only=ro, system=sys_, archive=arc)
    dest = tmp_path / "out.img"
    img.save(dest)
    return CpmImage(bytearray(dest.read_bytes()), geom)


def test_write_read_single_extent(tmp_path):
    """A small file written out reads back byte-exact.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")
    content = bytes(range(256)) * 2  # 512 bytes
    reopened = _roundtrip(geom, {"HELLO.TXT": content}, tmp_path)
    assert [f.name for f in reopened.list_files()] == ["HELLO.TXT"]
    assert reopened.read_file("HELLO.TXT") == content


def test_write_multi_extent(tmp_path):
    """A file larger than one 16 KiB extent spans multiple entries and round-trips.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")  # extent_mask == 0: one 16 KiB extent per entry
    content = bytes((i * 7) & 0xFF for i in range(40 * 1024))  # 40 KiB → 3 entries
    reopened = _roundtrip(geom, {"BIG.DAT": content}, tmp_path)
    entry = reopened.list_files()[0]
    assert entry.name == "BIG.DAT" and entry.size_bytes == 40 * 1024
    assert reopened.read_file("BIG.DAT") == content


def test_write_16bit_pointers(tmp_path):
    """A 16-bit-pointer geometry (wbw_hd1k) round-trips several files.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("wbw_hd1k")  # 16-bit AL, 4 KiB blocks
    files = {
        "A.TXT": bytes([1]) * 128,
        "B.TXT": bytes([2]) * 4096,
        "C.DAT": bytes([3]) * (12 * 1024),  # three blocks
    }
    reopened = _roundtrip(geom, files, tmp_path)
    assert {f.name for f in reopened.list_files()} == set(files)
    for name, content in files.items():
        assert reopened.read_file(name) == content


def test_write_empty_and_odd_length(tmp_path):
    """A zero-length file and a non-record-multiple file round-trip (record-granular).

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")
    reopened = _roundtrip(geom, {"EMPTY": b"", "ODD.BIN": bytes([0xAA]) * 1000}, tmp_path)
    listed = {f.name: f.size_bytes for f in reopened.list_files()}
    assert listed["EMPTY"] == 0
    assert reopened.read_file("EMPTY") == b""
    # 1000 bytes rounds up to 8 records = 1024 bytes, content preserved with zero tail.
    assert listed["ODD.BIN"] == 1024
    assert reopened.read_file("ODD.BIN")[:1000] == bytes([0xAA]) * 1000


def test_write_preserves_attributes(tmp_path):
    """Read-only / system / archive flags survive the round-trip.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")
    reopened = _roundtrip(
        geom, {"SYS.COM": bytes([1]) * 128}, tmp_path, attrs={"SYS.COM": (True, True, False)}
    )
    entry = reopened.list_files()[0]
    assert (entry.read_only, entry.system, entry.archive) == (True, True, False)


def test_write_matches_synthetic_builder(make_image_fn, tmp_path):
    """The writer and the independent conftest builder decode to the same files.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")
    files = {"ONE.TXT": bytes([1]) * 256, "TWO.DAT": bytes([2]) * 4096}
    from_builder = CpmImage(make_image_fn(geom, files), geom)
    from_writer = _roundtrip(geom, files, tmp_path)
    assert {f.name: f.size_bytes for f in from_builder.list_files()} == {
        f.name: f.size_bytes for f in from_writer.list_files()
    }
    for name in files:
        assert from_builder.read_file(name) == from_writer.read_file(name)


def test_boot_tracks_preserved(tmp_path):
    """The reserved/boot region is copied verbatim; only the data area is rebuilt.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("wbw_fd144")  # boottrk > 0
    assert geom.boottrk > 0
    raw = _blank(geom)
    boot_len = geom.offset + geom.boottrk * geom.sectrk * geom.seclen
    marker = bytes(range(256)) * (boot_len // 256 + 1)
    raw[:boot_len] = marker[:boot_len]  # stamp a recognisable boot region

    img = CpmImage(raw, geom)
    img.write_file("NEW.TXT", bytes([9]) * 512)
    dest = tmp_path / "boot.img"
    img.save(dest)

    written = dest.read_bytes()
    assert written[:boot_len] == marker[:boot_len]
    assert CpmImage(bytearray(written), geom).read_file("NEW.TXT") == bytes([9]) * 512


def test_delete_frees_blocks_for_reuse(tmp_path):
    """Deleting a file releases its blocks so a later write reuses them.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")
    img = CpmImage(_blank(geom), geom)
    img.write_file("A.TXT", bytes([1]) * 1024)
    img.write_file("B.TXT", bytes([2]) * 1024)
    img.delete_file("A.TXT")
    assert [f.name for f in img.list_files()] == ["B.TXT"]
    # C reuses the block A freed (lowest-free allocation), and B is intact.
    img.write_file("C.TXT", bytes([3]) * 1024)
    dest = tmp_path / "reuse.img"
    img.save(dest)
    reopened = CpmImage(bytearray(dest.read_bytes()), geom)
    assert {f.name for f in reopened.list_files()} == {"B.TXT", "C.TXT"}
    assert reopened.read_file("B.TXT") == bytes([2]) * 1024
    assert reopened.read_file("C.TXT") == bytes([3]) * 1024


def test_disk_full_raises(tmp_path):
    """A file needing more blocks than the data area holds raises DiskFullError.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")
    img = CpmImage(_blank(geom), geom)
    too_big = bytes(1) * ((geom.dsm + 2) * geom.blocksize)
    with pytest.raises(DiskFullError):
        img.write_file("HUGE.BIN", too_big)


def test_directory_full_raises():
    """More files than ``maxdir`` slots raises DirectoryFullError.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")
    img = CpmImage(_blank(geom), geom)
    with pytest.raises(DirectoryFullError):
        for i in range(geom.maxdir + 1):
            img.write_file(f"F{i}.TXT", bytes([0]) * 128)


def test_invalid_name_raises():
    """A name that is not valid CP/M 8.3 raises InvalidNameError and writes nothing.

    Verifies: FR-174, DR-050.
    """
    geom = _geom("ibm-3740")
    img = CpmImage(_blank(geom), geom)
    for bad in ("TOOLONGNAME.TXT", "A.LONGEXT", "HAS SPACE.TXT", "STAR*.TXT", ""):
        with pytest.raises(InvalidNameError):
            img.write_file(bad, b"x")
    assert img.list_files() == []


def test_split_83_normalises():
    """split_83 upper-cases and separates base/type; rejects bad names.

    Verifies: FR-174.
    """
    assert split_83("hello.txt") == ("HELLO", "TXT")
    assert split_83("readme") == ("README", "")
    with pytest.raises(InvalidNameError):
        split_83("bad.name.ext")
