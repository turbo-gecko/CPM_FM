"""CP/M disk geometry model and logical→physical sector mapping.

Pure data + arithmetic; no image I/O and (per CR-014) no GUI-toolkit imports.

A CP/M raw-sector image carries **no** geometry of its own (DR-048), so every
byte offset is derived from a :class:`DiskDef` (a parsed cpmtools ``diskdef``
stanza). This module owns that model and the skew/interleave permutation.

Satisfies: DR-048, DR-049, CR-014.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# One CP/M logical extent is 128 records of 128 bytes = 16 KiB, regardless of the
# physical block size (DR-049).
RECORD_SIZE = 128
EXTENT_SIZE = 128 * RECORD_SIZE  # 16384


@dataclass(frozen=True)
class DiskDef:
    """A single geometry definition (one cpmtools ``diskdef … end`` stanza).

    The mandatory fields mirror the cpmtools ``diskdefs`` grammar (DR-048);
    ``offset``/``libdsk_format``/``skewtab`` are optional and tolerated.

    Satisfies: DR-048.
    """

    name: str
    seclen: int
    tracks: int
    sectrk: int
    blocksize: int
    maxdir: int
    skew: int = 0
    boottrk: int = 0
    os: str = "2.2"
    offset: int = 0
    libdsk_format: str = ""
    skewtab: tuple[int, ...] = field(default_factory=tuple)

    @property
    def total_bytes(self) -> int:
        """Total image size this geometry describes (used for size-matching, FR-170)."""
        return self.tracks * self.sectrk * self.seclen + self.offset

    @property
    def records_per_block(self) -> int:
        return self.blocksize // RECORD_SIZE

    @property
    def sectors_per_block(self) -> int:
        return self.blocksize // self.seclen

    @property
    def data_tracks(self) -> int:
        """Tracks available for the filesystem (after the reserved/boot tracks)."""
        return self.tracks - self.boottrk

    @property
    def dsm(self) -> int:
        """Highest data-block number (block count − 1), the cpmtools ``dsm``.

        The directory occupies the first blocks of this data area (DR-049).
        """
        return (self.data_tracks * self.sectrk * self.seclen) // self.blocksize - 1

    @property
    def ptr16(self) -> bool:
        """True when allocation pointers are 16-bit (block count > 255) — DR-049."""
        return self.dsm >= 256

    @property
    def ptrs_per_entry(self) -> int:
        """Allocation-map pointers per 32-byte directory entry (8 if 16-bit, else 16)."""
        return 8 if self.ptr16 else 16

    @property
    def extents_per_entry(self) -> int:
        """Number of 16 KiB logical extents one directory entry addresses (≥ 1)."""
        return max(1, (self.ptrs_per_entry * self.blocksize) // EXTENT_SIZE)

    @property
    def extent_mask(self) -> int:
        """cpmtools ``exm``: the low bits of the extent counter held within one entry."""
        return self.extents_per_entry - 1


def build_skew_table(sectrk: int, skew: int) -> list[int]:
    """Return ``table[logical_sector] -> physical_sector`` for a track.

    Reproduces the cpmtools skew-table construction: starting at physical 0 and
    stepping by ``skew`` (mod ``sectrk``), skipping already-assigned physical
    sectors. ``skew`` 0/1 yields the identity permutation (common for raw and CF
    images). The same table applies to every track.

    Satisfies: DR-049.
    """
    if sectrk <= 0:
        return []
    if skew <= 1:
        return list(range(sectrk))
    table: list[int] = []
    j = 0
    for _ in range(sectrk):
        while j in table:
            j = (j + 1) % sectrk
        table.append(j)
        j = (j + skew) % sectrk
    return table
