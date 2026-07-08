"""Tests for the cpmtools ``diskdefs`` parser and the bundled database.

Verifies: DR-048.
"""

from __future__ import annotations

import pytest

from cpm_fm.utils.disk_image import load_diskdefs
from cpm_fm.utils.disk_image.diskdefs import DiskDefError, parse_diskdefs


def test_parse_single_stanza():
    """A well-formed stanza parses into the expected field values.

    Verifies: DR-048.
    """
    (d,) = parse_diskdefs(
        """
        # a comment
        diskdef sample
          seclen 128
          tracks 77
          sectrk 26
          blocksize 1024
          maxdir 64
          skew 6
          boottrk 2
          os 2.2
        end
        """
    )
    assert d.name == "sample"
    assert (d.seclen, d.tracks, d.sectrk, d.blocksize, d.maxdir) == (128, 77, 26, 1024, 64)
    assert d.skew == 6 and d.boottrk == 2
    assert d.total_bytes == 77 * 26 * 128


def test_bundled_diskdefs_load_and_cover_expected_names():
    """The shipped database parses and contains the documented definitions.

    Verifies: DR-048.
    """
    defs = load_diskdefs()
    names = set(defs.names())
    assert {
        "ibm-3740",
        "osborne1",
        "kaypro2",
        "wbw_fd144",
        "wbw_hd1k",
        "wbw_hd512",
        "rc2014",
    } <= names
    hd1k = defs.get("wbw_hd1k")
    assert hd1k is not None
    assert hd1k.total_bytes == 8 * 1024 * 1024  # 8 MiB pure-filesystem slice


def test_bundled_diskdefs_match_romwbw_image_sizes():
    """The RomWBW definitions size-match their real image families (FR-170).

    Verifies: DR-048.
    """
    defs = load_diskdefs()
    assert defs.get("wbw_fd144").total_bytes == 1474560
    assert defs.get("wbw_hd512").total_bytes == 8519680
    assert defs.get("wbw_hd1k").total_bytes == 8388608


def test_bundled_diskdefs_include_v29_additions():
    """The v2.29 broadened coverage is present with correct sizes.

    Verifies: DR-048.
    """
    defs = load_diskdefs()
    names = set(defs.names())
    assert {
        "wbw_rom128",
        "wbw_rom256",
        "wbw_rom384",
        "wbw_rom896",
        "4mb-hd",
        "pcw",
        "epsqx10",
        "alpha",
        "interak",
    } <= names
    assert defs.get("wbw_rom128").total_bytes == 4 * 64 * 512
    assert defs.get("4mb-hd").total_bytes == 1024 * 32 * 128
    assert defs.get("pcw").total_bytes == 40 * 9 * 512


def test_offset_with_track_suffix_resolves_to_bytes():
    """A cpmtools ``offset`` with a ``T`` (tracks) suffix resolves to bytes.

    Verifies: DR-048.
    """
    (d,) = parse_diskdefs(
        """
        diskdef slice1
          seclen 512
          tracks 1024
          sectrk 16
          blocksize 4096
          maxdir 1024
          offset 1040T
        end
        """
    )
    assert d.offset == 1040 * 16 * 512  # tracks * sectrk * seclen


def test_offset_with_kilobyte_suffix():
    """An ``offset`` with a ``K`` suffix scales by 1024.

    Verifies: DR-048.
    """
    (d,) = parse_diskdefs(
        "diskdef x\n seclen 512\n tracks 8\n sectrk 16\n"
        " blocksize 4096\n maxdir 64\n offset 1024K\nend\n"
    )
    assert d.offset == 1024 * 1024


def test_missing_required_field_raises():
    """A stanza missing a required field raises a clear error.

    Verifies: DR-048.
    """
    with pytest.raises(DiskDefError):
        parse_diskdefs("diskdef bad\n  seclen 128\nend\n")


def test_unterminated_stanza_raises():
    """A stanza with no ``end`` raises.

    Verifies: DR-048.
    """
    with pytest.raises(DiskDefError):
        parse_diskdefs("diskdef bad\n  seclen 128\n  tracks 1\n")
