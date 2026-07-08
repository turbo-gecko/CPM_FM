"""Tests for the geometry model and the skew/interleave permutation.

Verifies: DR-048, DR-049.
"""

from __future__ import annotations

from cpm_fm.utils.disk_image.geometry import DiskDef, build_skew_table


def test_skew_zero_and_one_are_identity():
    """Skew 0 and 1 map logical sectors straight through.

    Verifies: DR-049.
    """
    assert build_skew_table(9, 0) == list(range(9))
    assert build_skew_table(26, 1) == list(range(26))


def test_skew_table_is_a_permutation_with_no_collisions():
    """A skewed table is a bijection over the sector range.

    Verifies: DR-049.
    """
    for sectrk, skew in [(26, 6), (10, 2), (32, 5)]:
        table = build_skew_table(sectrk, skew)
        assert sorted(table) == list(range(sectrk))


def test_skew_table_known_sequence():
    """The IBM-3740 skew (6-way interleave over 26 sectors) matches cpmtools.

    Verifies: DR-049.
    """
    # Stepping by 6, skipping used slots: 0,6,12,18,24,(30->4)...
    table = build_skew_table(26, 6)
    assert table[:5] == [0, 6, 12, 18, 24]


def test_pointer_width_and_extent_mask():
    """Derived geometry: 8-bit vs 16-bit pointers and the extent mask.

    Verifies: DR-049.
    """
    small = DiskDef("s", seclen=128, tracks=77, sectrk=26, blocksize=1024, maxdir=64, boottrk=2)
    assert small.ptr16 is False  # dsm < 256
    assert small.ptrs_per_entry == 16
    assert small.extent_mask == 0

    big = DiskDef("b", seclen=512, tracks=512, sectrk=32, blocksize=4096, maxdir=512, boottrk=0)
    assert big.ptr16 is True  # dsm >= 256
    assert big.ptrs_per_entry == 8
    assert big.extent_mask == 1
