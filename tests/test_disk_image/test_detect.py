"""Tests for geometry auto-detection ranking and ambiguity flagging.

Verifies: FR-170, FR-172.
"""

from __future__ import annotations

import pytest

from cpm_fm.utils.disk_image import (
    DetectResult,
    detect_diskdef,
    is_ambiguous,
    load_diskdefs,
)


# Definitions whose total size is unique in the bundled database, so a synthetic
# image of that size detects unambiguously. (The 8 MiB wbw_hd1k / rc2014 pair
# deliberately collides and is covered by test_eight_mb_images_are_ambiguous.)
@pytest.mark.parametrize(
    "defname", ["ibm-3740", "osborne1", "kaypro2", "wbw_fd144", "wbw_fd720", "wbw_hd512"]
)
def test_detect_ranks_correct_geometry_first(tmp_path, make_image_fn, defname):
    """Each uniquely-sized bundled geometry's synthetic image detects as top candidate.

    Verifies: FR-170.
    """
    defs = load_diskdefs()
    geom = defs.get(defname)
    raw = make_image_fn(geom, {"FILE.TXT": bytes([1]) * 128})
    path = tmp_path / "d.img"
    path.write_bytes(raw)

    results = detect_diskdef(str(path), defs)
    assert results, "expected at least one candidate"
    assert results[0].diskdef.name == defname
    assert not is_ambiguous(results)


def test_eight_mb_images_are_ambiguous(tmp_path, make_image_fn):
    """A near-empty 8 MiB image matches both wbw_hd1k and rc2014 → ambiguous (FR-170).

    A disk that uses only low blocks decodes identically under both geometries, so
    detection stays ambiguous; the capacity tie-break still ranks the more
    capacious wbw_hd1k first so the auto-default never truncates the directory.

    Verifies: FR-170.
    """
    defs = load_diskdefs()
    raw = make_image_fn(defs.get("wbw_hd1k"), {"FILE.TXT": bytes([1]) * 128})
    path = tmp_path / "d.img"
    path.write_bytes(raw)

    results = detect_diskdef(str(path), defs)
    names = {r.diskdef.name for r in results}
    assert {"wbw_hd1k", "rc2014"} <= names
    assert is_ambiguous(results)  # the GUI prompts the user to choose
    assert results[0].diskdef.name == "wbw_hd1k"  # capacity tie-break default


def _kaypro2_dir_full(al_byte: int) -> bytes:
    """A kaypro2-sized raw image (skew 0, 8-bit pointers) whose directory is full of
    in-use entries that each reference block ``al_byte``.

    kaypro2 has ``dsm`` 194, so ``al_byte`` 5 is a real data block and 250 is an
    impossible one — letting a test exercise the allocation-pointer range check
    without reproducing a non-trivial skew.
    """
    geom = load_diskdefs().get("kaypro2")
    raw = bytearray([0xE5]) * geom.total_bytes
    base = geom.boottrk * geom.sectrk * geom.seclen  # skew 0 → directory is contiguous
    for i in range(geom.maxdir):
        rec = bytearray(32)
        rec[0] = 0  # user 0 (in-use)
        rec[1:9] = f"F{i:06d}".encode("ascii").ljust(8)
        rec[9:12] = b"BIN"
        rec[15] = 1  # record count
        rec[16] = al_byte  # 8-bit allocation pointer
        raw[base + i * 32 : base + i * 32 + 32] = rec
    return bytes(raw)


def test_out_of_range_allocation_pointers_reject_geometry(tmp_path):
    """A same-size file whose directory pointers exceed the data area is rejected.

    An in-range pointer set is accepted as kaypro2; an impossible one (block 250 >
    dsm 194) scores every entry invalid, so the geometry drops below the
    confidence floor and is not offered.

    Verifies: FR-170.
    """
    defs = load_diskdefs()
    good = tmp_path / "good.img"
    good.write_bytes(_kaypro2_dir_full(5))
    bad = tmp_path / "bad.img"
    bad.write_bytes(_kaypro2_dir_full(250))

    assert any(r.diskdef.name == "kaypro2" for r in detect_diskdef(str(good), defs))
    assert all(r.diskdef.name != "kaypro2" for r in detect_diskdef(str(bad), defs))


def test_detect_returns_empty_for_foreign_file(tmp_path):
    """A garbage file whose size matches nothing yields no candidates.

    Verifies: FR-170, FR-172.
    """
    path = tmp_path / "junk.bin"
    path.write_bytes(bytes([0x5A]) * 12345)  # not any bundled size
    assert detect_diskdef(str(path), load_diskdefs()) == []


def test_detect_returns_empty_for_zero_byte_file(tmp_path):
    """A zero-byte file yields no candidates.

    Verifies: FR-170, FR-172.
    """
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    assert detect_diskdef(str(path), load_diskdefs()) == []


def test_is_ambiguous_logic():
    """Ambiguity: empty, single, close-scored, and clear-winner cases.

    Verifies: FR-170.
    """
    d = load_diskdefs().get("ibm-3740")
    assert is_ambiguous([]) is True
    assert is_ambiguous([DetectResult(d, 0.9, 1)]) is False
    close = [DetectResult(d, 0.90, 1), DetectResult(d, 0.88, 1)]
    assert is_ambiguous(close) is True
    clear = [DetectResult(d, 0.98, 1), DetectResult(d, 0.70, 1)]
    assert is_ambiguous(clear) is False
