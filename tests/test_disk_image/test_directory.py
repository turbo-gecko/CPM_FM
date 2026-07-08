"""Tests for directory parsing, file listing and content reconstruction.

Verifies: FR-169, FR-171, DR-049.
"""

from __future__ import annotations

from cpm_fm.utils.disk_image import load_diskdefs
from cpm_fm.utils.disk_image.image import CpmImage


def _geom(name):
    d = load_diskdefs().get(name)
    assert d is not None
    return d


def test_list_and_read_single_extent(make_image_fn):
    """A small file lists once and reads back byte-exact.

    Verifies: FR-169, FR-171, DR-049.
    """
    geom = _geom("ibm-3740")
    content = bytes(range(256)) * 2  # 512 bytes, multiple of 128
    raw = make_image_fn(geom, {"HELLO.TXT": content})
    img = CpmImage(raw, geom)

    names = [f.name for f in img.list_files()]
    assert names == ["HELLO.TXT"]
    assert img.list_files()[0].size_bytes == 512
    assert img.read_file("HELLO.TXT") == content
    # lookup is case-insensitive on the NAME.EXT form
    assert img.read_file("hello.txt") == content


def test_multi_extent_file(make_image_fn):
    """A file larger than one 16 KiB extent spans multiple directory entries.

    Verifies: FR-171, DR-049.
    """
    geom = _geom("ibm-3740")  # extent_mask == 0: each entry holds one 16 KiB extent
    content = bytes((i * 7) & 0xFF for i in range(20 * 1024))  # 20 KiB, > one extent
    raw = make_image_fn(geom, {"BIG.DAT": content})
    img = CpmImage(raw, geom)

    entry = img.list_files()[0]
    assert entry.name == "BIG.DAT"
    assert entry.size_bytes == 20 * 1024
    assert img.read_file("BIG.DAT") == content


def test_record_tail_truncation(make_image_fn):
    """A non-record-multiple file is truncated to its record-rounded length.

    Verifies: FR-171, DR-049.
    """
    geom = _geom("ibm-3740")
    content = bytes([0xAA]) * 1000  # rounds up to 8 records = 1024 bytes
    raw = make_image_fn(geom, {"ODD.BIN": content})
    img = CpmImage(raw, geom)

    data = img.read_file("ODD.BIN")
    assert len(data) == 1024
    assert data[:1000] == content


def test_empty_file(make_image_fn):
    """A zero-length file lists with size 0 and reads back empty.

    Verifies: FR-169, FR-171.
    """
    geom = _geom("ibm-3740")
    raw = make_image_fn(geom, {"EMPTY": b""})
    img = CpmImage(raw, geom)
    entry = img.list_files()[0]
    assert entry.name == "EMPTY" and entry.size_bytes == 0
    assert img.read_file("EMPTY") == b""


def test_attributes_decoded(make_image_fn):
    """Read-only / system / archive flags are decoded from the type high bits.

    Verifies: DR-049.
    """
    geom = _geom("ibm-3740")
    raw = make_image_fn(
        geom,
        {"SYS.COM": bytes([1]) * 128},
        attrs={"SYS.COM": (True, True, False)},
    )
    entry = CpmImage(raw, geom).list_files()[0]
    assert entry.read_only is True
    assert entry.system is True
    assert entry.archive is False


def test_multiple_files_and_16bit_pointers(make_image_fn):
    """Several files on a 16-bit-pointer geometry (wbw_hd1k) list and read back.

    Verifies: FR-169, FR-171, DR-049.
    """
    geom = _geom("wbw_hd1k")  # 16-bit allocation pointers, 4 KiB blocks
    files = {
        "A.TXT": bytes([1]) * 128,
        "B.TXT": bytes([2]) * 4096,  # exactly one block
        "C.DAT": bytes([3]) * (8 * 1024),  # two blocks, still one extent-entry
    }
    img = CpmImage(make_image_fn(geom, files), geom)
    listed = {f.name: f.size_bytes for f in img.list_files()}
    assert set(listed) == {"A.TXT", "B.TXT", "C.DAT"}
    for name, content in files.items():
        assert img.read_file(name) == content
