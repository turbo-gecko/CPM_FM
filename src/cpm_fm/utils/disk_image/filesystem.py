"""High-level CP/M file operations built on the directory + image layers.

Groups directory extents into logical files and reconstructs file bytes by
following the extent order and per-extent allocation maps (DR-049), and — for the
write path — encodes a file's allocated blocks back into 32-byte directory
records (DR-050). Pure ``utils`` layer — no GUI imports (CR-014).

Satisfies: FR-169, FR-171, FR-174, DR-049, DR-050, CR-014.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cpm_fm.utils.disk_image.directory import CpmDirEntry
from cpm_fm.utils.disk_image.geometry import RECORD_SIZE, DiskDef

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cpm_fm.utils.disk_image.image import CpmImage

# CP/M 8.3 name characters CP/M reserves as delimiters / illegal in a filename.
_ILLEGAL_NAME_CHARS = set("<>.,;:=?*[]|/\\ ")


class ImageWriteError(Exception):
    """Base class for the write-path failures surfaced by FR-174 (DR-050)."""


class DiskFullError(ImageWriteError):
    """The file set needs more data blocks than the geometry provides (DR-050)."""


class DirectoryFullError(ImageWriteError):
    """The file set needs more directory entries than ``maxdir`` allows (DR-050)."""


class InvalidNameError(ImageWriteError):
    """A name is not a valid CP/M 8.3 filename (FR-174)."""


@dataclass
class CpmFileEntry:
    """A logical file as presented to callers (FR-169)."""

    name: str  # "NAME.EXT", upper case
    size_bytes: int
    user: int
    read_only: bool
    system: bool
    archive: bool


def _extent_records(entry: CpmDirEntry, exm: int) -> int:
    """Records held by a single directory entry (DR-049).

    ``(ex & exm)`` counts the complete 16 KiB sub-extents ahead of the current
    one within this entry; ``rc`` is the record count of the current sub-extent.
    A fully-used entry therefore yields ``(exm + 1) * 128`` records.
    """
    return (entry.ex & exm) * 128 + entry.rc


def list_files(entries: list[CpmDirEntry], geom: DiskDef) -> list[CpmFileEntry]:
    """Collapse directory extents into one entry per logical file (FR-169).

    Size is the CP/M record-granular length (a multiple of 128 bytes) summed over
    every extent of the file. Attribute flags are OR-ed across extents.

    Satisfies: FR-169, DR-049.
    """
    exm = geom.extent_mask
    files: dict[tuple[int, str, str], CpmFileEntry] = {}
    order: list[tuple[int, str, str]] = []
    for e in entries:
        recs = _extent_records(e, exm)
        existing = files.get(e.key)
        if existing is None:
            files[e.key] = CpmFileEntry(
                name=e.full_name,
                size_bytes=recs * RECORD_SIZE,
                user=e.user,
                read_only=e.read_only,
                system=e.system,
                archive=e.archive,
            )
            order.append(e.key)
        else:
            existing.size_bytes += recs * RECORD_SIZE
            existing.read_only = existing.read_only or e.read_only
            existing.system = existing.system or e.system
            existing.archive = existing.archive or e.archive
    return [files[k] for k in order]


def read_file(
    image: CpmImage, entries: list[CpmDirEntry], name: str, user: int | None = None
) -> bytes:
    """Return the byte content of the file called ``name`` (FR-171).

    The file's extents are ordered by extent number; each extent contributes its
    used allocation blocks in order, and the whole is truncated to the record
    length implied by the final extent (DR-049). Lookup is case-insensitive on
    the ``NAME.EXT`` form. When ``user`` is given the match is further restricted
    to that user area, so the same name in two areas (FR-185) reads the intended
    file rather than whichever extent happens to be found first.

    Raises ``KeyError`` when no such file exists.

    Satisfies: FR-171, FR-185, DR-049.
    """
    target = name.upper()
    matching = [e for e in entries if e.full_name == target and (user is None or e.user == user)]
    if not matching:
        raise KeyError(name)

    geom = image.geom
    exm = geom.extent_mask
    recs_per_block = geom.records_per_block
    matching.sort(key=lambda e: e.extent_index)

    out = bytearray()
    total_records = 0
    for e in matching:
        recs = _extent_records(e, exm)
        total_records += recs
        nblocks = (recs + recs_per_block - 1) // recs_per_block
        used = [b for b in e.al if b != 0][:nblocks]
        for block in used:
            out += image.read_block(block)
    del out[total_records * RECORD_SIZE :]
    return bytes(out)


def split_83(name: str) -> tuple[str, str]:
    """Split ``name`` into an upper-case (base, type) pair, validating CP/M 8.3 (FR-174).

    The base must be 1–8 characters and the type 0–3, drawn from the printable
    ASCII set excluding the CP/M filename delimiters (``<>.,;:=?*[]|/\\`` and
    space). Raises :class:`InvalidNameError` on any violation so the write path
    aborts rather than emitting a malformed directory entry.

    Satisfies: FR-174, DR-050.
    """
    base, _, ext = name.strip().upper().rpartition(".")
    if not base:  # no dot → rpartition puts the whole name in ``ext``
        base, ext = ext, ""
    if not (1 <= len(base) <= 8) or len(ext) > 3:
        raise InvalidNameError(name)
    for ch in base + ext:
        if not (0x21 <= ord(ch) <= 0x7E) or ch in _ILLEGAL_NAME_CHARS:
            raise InvalidNameError(name)
    return base, ext


def _encode_al(blocks: list[int], geom: DiskDef) -> bytes:
    """Serialise ``blocks`` (already ≤ ``ptrs_per_entry``) as the 16-byte AL map (DR-050)."""
    ptrs = geom.ptrs_per_entry
    padded = (blocks + [0] * ptrs)[:ptrs]
    if geom.ptr16:
        return b"".join(struct.pack("<H", p) for p in padded)
    return bytes(padded)


def build_dir_entries(
    user: int,
    base: str,
    ext: str,
    read_only: bool,
    system: bool,
    archive: bool,
    blocks: list[int],
    nrec: int,
    geom: DiskDef,
) -> list[bytes]:
    """Encode one logical file as its 32-byte directory records (DR-050).

    Inverts :func:`read_file`/:func:`list_files`: ``blocks`` (the file's allocated
    data-block numbers, in order) and the record count ``nrec`` are split across as
    many directory entries as the geometry needs — each entry addressing at most
    ``ptrs_per_entry`` blocks / ``extents_per_entry`` 16 KiB extents — with the
    extent counters ``EX``/``S2`` and record count ``RC`` set so the reader
    reconstructs exactly ``nrec`` records. An empty file yields a single
    zero-length entry. Attribute flags are written as the high bit of the three
    type bytes, matching :func:`~cpm_fm.utils.disk_image.directory.parse_directory`.

    Satisfies: FR-174, DR-050.
    """
    name_bytes = base.ljust(8)[:8].encode("ascii")
    type_bytes = bytearray(ext.ljust(3)[:3].encode("ascii"))
    if read_only:
        type_bytes[0] |= 0x80
    if system:
        type_bytes[1] |= 0x80
    if archive:
        type_bytes[2] |= 0x80

    caps_records = geom.extents_per_entry * 128
    ptrs = geom.ptrs_per_entry
    rpb = geom.records_per_block
    n_entries = max(1, -(-nrec // caps_records))

    records: list[bytes] = []
    for i in range(n_entries):
        entry_recs = min(caps_records, nrec - i * caps_records)
        full_sub = 0 if entry_recs == 0 else (entry_recs - 1) // 128
        rc = entry_recs - full_sub * 128  # 0 for an empty file, else 1..128
        x = i * geom.extents_per_entry + full_sub
        ex_byte = x & 0x1F
        s2_byte = (x >> 5) & 0x3F
        nblk = 0 if entry_recs == 0 else -(-entry_recs // rpb)
        entry_blocks = blocks[i * ptrs : i * ptrs + nblk]
        records.append(
            bytes([user & 0xFF])
            + name_bytes
            + bytes(type_bytes)
            + bytes([ex_byte, 0, s2_byte, rc])
            + _encode_al(entry_blocks, geom)
        )
    return records
