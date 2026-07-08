"""CP/M directory-entry parsing (the 32-byte on-disk record).

Pure byte decoding; no image I/O, no GUI imports (CR-014).

Satisfies: DR-049, CR-014.
"""

from __future__ import annotations

from dataclasses import dataclass

DIR_ENTRY_SIZE = 32
EMPTY_USER = 0xE5  # a deleted / never-used directory slot
MAX_USER = 0x1F  # user numbers 0x00–0x1F are in-use file entries; ≥0x20 = label/timestamp


@dataclass
class CpmDirEntry:
    """One in-use 32-byte directory entry (DR-049)."""

    user: int
    name: str  # 1–8 chars, trailing spaces stripped
    ext: str  # 0–3 chars, trailing spaces stripped
    ex: int  # extent counter low
    s1: int
    s2: int  # extent counter high (module)
    rc: int  # record count for the last extent in this entry
    al: list[int]  # allocation block pointers (16-bit values already combined)
    read_only: bool
    system: bool
    archive: bool

    @property
    def full_name(self) -> str:
        """``NAME.EXT`` (upper case, no trailing dot when the type is empty)."""
        return f"{self.name}.{self.ext}" if self.ext else self.name

    @property
    def key(self) -> tuple[int, str, str]:
        """Identity shared by every extent of one logical file (DR-049)."""
        return (self.user, self.name, self.ext)

    @property
    def extent_index(self) -> int:
        """Combined logical-extent number used to order a file's extents (DR-049)."""
        return self.s2 * 32 + self.ex


def _clean(raw: bytes) -> str:
    """Mask the attribute high bit off each byte and return a stripped 7-bit string."""
    return bytes(b & 0x7F for b in raw).decode("ascii", errors="replace").rstrip()


def parse_directory(data: bytes, ptr16: bool) -> list[CpmDirEntry]:
    """Decode a directory region into its in-use file entries (DR-049).

    Entries with user byte ``0xE5`` (empty) or ``≥ 0x20`` (disk-label /
    timestamp records) are skipped. Allocation pointers are read as 8-bit or, when
    ``ptr16`` is set, 16-bit little-endian values.

    Satisfies: DR-049.
    """
    entries: list[CpmDirEntry] = []
    for off in range(0, len(data) - DIR_ENTRY_SIZE + 1, DIR_ENTRY_SIZE):
        rec = data[off : off + DIR_ENTRY_SIZE]
        user = rec[0]
        if user == EMPTY_USER or user > MAX_USER:
            continue
        name = _clean(rec[1:9])
        ext = _clean(rec[9:12])
        # Attribute flags live in the high bit of the three type bytes (DR-049).
        read_only = bool(rec[9] & 0x80)
        system = bool(rec[10] & 0x80)
        archive = bool(rec[11] & 0x80)
        ex, s1, s2, rc = rec[12], rec[13], rec[14], rec[15]
        al_bytes = rec[16:32]
        if ptr16:
            al = [al_bytes[i] | (al_bytes[i + 1] << 8) for i in range(0, 16, 2)]
        else:
            al = list(al_bytes)
        entries.append(
            CpmDirEntry(
                user=user,
                name=name,
                ext=ext,
                ex=ex,
                s1=s1,
                s2=s2,
                rc=rc,
                al=al,
                read_only=read_only,
                system=system,
                archive=archive,
            )
        )
    return entries
