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
    """An 8 MiB image matches both wbw_hd1k and rc2014 → flagged ambiguous (FR-170).

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
