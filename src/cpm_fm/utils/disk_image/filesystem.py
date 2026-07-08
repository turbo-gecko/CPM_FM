"""High-level CP/M file operations built on the directory + image layers.

Groups directory extents into logical files and reconstructs file bytes by
following the extent order and per-extent allocation maps (DR-049). Pure
``utils`` layer — no GUI imports (CR-014).

Satisfies: FR-169, FR-171, DR-049, CR-014.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cpm_fm.utils.disk_image.directory import CpmDirEntry
from cpm_fm.utils.disk_image.geometry import RECORD_SIZE, DiskDef

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cpm_fm.utils.disk_image.image import CpmImage


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


def read_file(image: CpmImage, entries: list[CpmDirEntry], name: str) -> bytes:
    """Return the byte content of the file called ``name`` (FR-171).

    The file's extents are ordered by extent number; each extent contributes its
    used allocation blocks in order, and the whole is truncated to the record
    length implied by the final extent (DR-049). Lookup is case-insensitive on
    the ``NAME.EXT`` form.

    Raises ``KeyError`` when no such file exists.

    Satisfies: FR-171, DR-049.
    """
    target = name.upper()
    matching = [e for e in entries if e.full_name == target]
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
