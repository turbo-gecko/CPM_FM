"""``CpmImage`` — a mounted raw-sector CP/M image bound to a geometry.

Owns the skew-aware sector reader that turns a data-area byte range into bytes,
and composes :mod:`directory` + :mod:`filesystem` to list and read files. Pure
``utils`` layer: no GUI imports (CR-014).

Satisfies: FR-169, FR-172, DR-049, CR-014.
"""

from __future__ import annotations

from pathlib import Path

from cpm_fm.utils.disk_image import filesystem
from cpm_fm.utils.disk_image.directory import (
    DIR_ENTRY_SIZE,
    EMPTY_USER,
    MAX_USER,
    CpmDirEntry,
    parse_directory,
)
from cpm_fm.utils.disk_image.filesystem import (
    CpmFileEntry,
    DirectoryFullError,
    DiskFullError,
    build_dir_entries,
    split_83,
)
from cpm_fm.utils.disk_image.geometry import RECORD_SIZE, DiskDef, build_skew_table


class CpmImage:
    """A CP/M filesystem read from ``raw`` bytes using geometry ``geom``.

    ``raw`` is a single filesystem slice (offset already applied by the caller for
    multi-slice CF media). Construction parses the directory eagerly; a
    structurally impossible image (too small for the reserved tracks + directory)
    raises ``ValueError`` so :func:`~cpm_fm.utils.disk_image.open_image` can turn
    it into a ``None`` result rather than crashing the GUI (FR-172).

    Satisfies: FR-169, FR-172, DR-049.
    """

    def __init__(self, raw: bytes, geom: DiskDef):
        self.geom = geom
        self._raw = bytearray(raw)  # mutable: the write path edits it in place (DR-050)
        self._skew = build_skew_table(geom.sectrk, geom.skew)
        need = geom.offset + geom.boottrk * geom.sectrk * geom.seclen + geom.maxdir * 32
        if len(raw) < need:
            raise ValueError("image too small for the selected geometry")
        self._dir_entries: list[CpmDirEntry] = parse_directory(self._read_directory(), geom.ptr16)

    # --- skew-aware raw access ------------------------------------------------

    def _read_data(self, pos: int, length: int) -> bytes:
        """Read ``length`` bytes from data-area offset ``pos`` (after boot tracks).

        Each logical sector is remapped to its physical sector via the skew table
        before being read, so interleaved images are decoded correctly (DR-049).
        Reads past the end of the backing bytes yield zero padding rather than an
        error (tolerant of slightly-short images — FR-172).

        Satisfies: DR-049, FR-172.
        """
        g = self.geom
        track_bytes = g.sectrk * g.seclen
        first_data_sec = g.boottrk * g.sectrk
        out = bytearray()
        p = pos
        end = pos + length
        while p < end:
            sec_index = first_data_sec + p // g.seclen
            track, logsec = divmod(sec_index, g.sectrk)
            phys = self._skew[logsec] if logsec < len(self._skew) else logsec
            sec_abs = g.offset + track * track_bytes + phys * g.seclen
            within = p % g.seclen
            take = min(g.seclen - within, end - p)
            chunk = self._raw[sec_abs + within : sec_abs + within + take]
            out += chunk
            if len(chunk) < take:  # short read near EOF → zero pad
                out += bytes(take - len(chunk))
            p += take
        return bytes(out)

    def _read_directory(self) -> bytes:
        return self._read_data(0, self.geom.maxdir * 32)

    def read_block(self, block: int) -> bytes:
        """Return the ``blocksize`` bytes of data block ``block`` (DR-049)."""
        return self._read_data(block * self.geom.blocksize, self.geom.blocksize)

    def _write_data(self, pos: int, data: bytes) -> None:
        """Write ``data`` to data-area offset ``pos``, applying skew (DR-050).

        The exact inverse of :meth:`_read_data`: each logical sector is remapped to
        its physical sector before the bytes land, so a written image is read back
        identically. The backing buffer is grown with zero padding if a write would
        run past its current end (it should not for a valid geometry).

        Satisfies: DR-050.
        """
        g = self.geom
        track_bytes = g.sectrk * g.seclen
        first_data_sec = g.boottrk * g.sectrk
        p = pos
        i = 0
        end = pos + len(data)
        while p < end:
            sec_index = first_data_sec + p // g.seclen
            track, logsec = divmod(sec_index, g.sectrk)
            phys = self._skew[logsec] if logsec < len(self._skew) else logsec
            sec_abs = g.offset + track * track_bytes + phys * g.seclen
            within = p % g.seclen
            take = min(g.seclen - within, end - p)
            need = sec_abs + within + take
            if len(self._raw) < need:
                self._raw.extend(b"\x00" * (need - len(self._raw)))
            self._raw[sec_abs + within : sec_abs + within + take] = data[i : i + take]
            p += take
            i += take

    def write_block(self, block: int, data: bytes) -> None:
        """Write data block ``block`` (padded/truncated to ``blocksize``) — DR-050."""
        bs = self.geom.blocksize
        chunk = data[:bs].ljust(bs, b"\x00")
        self._write_data(block * bs, chunk)

    # --- high-level API ------------------------------------------------------

    @property
    def entries(self) -> list[CpmDirEntry]:
        return self._dir_entries

    def list_files(self) -> list[CpmFileEntry]:
        """List the files on the image (FR-169).

        Satisfies: FR-169.
        """
        return filesystem.list_files(self._dir_entries, self.geom)

    def read_file(self, name: str, user: int | None = None) -> bytes:
        """Return the byte content of ``name`` ("NAME.EXT", case-insensitive) — FR-171.

        When ``user`` is given the lookup is restricted to that user area so a
        name present in more than one area reads the intended file (FR-185).

        Satisfies: FR-171, FR-185, DR-049.
        """
        return filesystem.read_file(self, self._dir_entries, name, user)

    # --- write path (FR-174, DR-050) -----------------------------------------

    def _first_data_block(self) -> int:
        """Lowest block available to files — the blocks after the directory (DR-050)."""
        bs = self.geom.blocksize
        return -(-(self.geom.maxdir * DIR_ENTRY_SIZE) // bs)

    def _used_blocks(self) -> set[int]:
        """Data blocks currently referenced by an in-use directory entry (DR-050).

        A well-formed entry zeroes its allocation slots past the last used block, so
        the set of non-zero ``AL`` pointers is exactly the in-use block set.
        """
        used: set[int] = set()
        for e in self._dir_entries:
            used.update(b for b in e.al if b != 0)
        return used

    def _free_dir_slot_offsets(self) -> list[int]:
        """Byte offsets of the empty (``0xE5``) directory slots, low first (DR-050)."""
        directory = self._read_directory()
        return [
            off for off in range(0, len(directory), DIR_ENTRY_SIZE) if directory[off] == EMPTY_USER
        ]

    def _erase(self, match) -> int:
        """Mark every in-use entry for which ``match(user, base, ext)`` holds free (DR-050).

        Sets the slot's user byte to ``0xE5`` in the backing buffer (the CP/M
        ``ERA`` semantics — the data blocks are simply released, not wiped) and
        re-parses the directory. Returns the number of slots erased.
        """
        directory = self._read_directory()
        erased = 0
        for off in range(0, len(directory) - DIR_ENTRY_SIZE + 1, DIR_ENTRY_SIZE):
            user = directory[off]
            if user == EMPTY_USER or user > MAX_USER:
                continue
            base = bytes(b & 0x7F for b in directory[off + 1 : off + 9]).decode("ascii").rstrip()
            ext = bytes(b & 0x7F for b in directory[off + 9 : off + 12]).decode("ascii").rstrip()
            if match(user, base, ext):
                self._write_data(off, b"\xe5")
                erased += 1
        if erased:
            self._dir_entries = parse_directory(self._read_directory(), self.geom.ptr16)
        return erased

    def write_file(
        self,
        name: str,
        data: bytes,
        user: int = 0,
        read_only: bool = False,
        system: bool = False,
        archive: bool = False,
    ) -> None:
        """Write ``data`` as file ``name`` into the in-memory image (FR-174, DR-050).

        Replaces any existing file of the same ``(user, name)``, allocates the
        lowest free data blocks, and appends the encoded directory entries. Raises
        :class:`~cpm_fm.utils.disk_image.filesystem.InvalidNameError`,
        :class:`~cpm_fm.utils.disk_image.filesystem.DiskFullError`, or
        :class:`~cpm_fm.utils.disk_image.filesystem.DirectoryFullError` (writing
        nothing) rather than truncating silently. Call :meth:`save` to persist.

        Satisfies: FR-174, DR-050.
        """
        base, ext = split_83(name)
        self._erase(lambda u, b, e: u == user and b == base and e == ext)

        g = self.geom
        nrec = -(-len(data) // RECORD_SIZE)
        nblk = -(-nrec // g.records_per_block) if nrec else 0
        used = self._used_blocks()
        free = [b for b in range(self._first_data_block(), g.dsm + 1) if b not in used]
        if nblk > len(free):
            raise DiskFullError(name)
        blocks = free[:nblk]

        records = build_dir_entries(user, base, ext, read_only, system, archive, blocks, nrec, g)
        slots = self._free_dir_slot_offsets()
        if len(records) > len(slots):
            raise DirectoryFullError(name)

        padded = data.ljust(nblk * g.blocksize, b"\x00")
        for idx, blk in enumerate(blocks):
            self.write_block(blk, padded[idx * g.blocksize : (idx + 1) * g.blocksize])
        for rec, off in zip(records, slots):
            self._write_data(off, rec)
        self._dir_entries = parse_directory(self._read_directory(), g.ptr16)

    def delete_file(self, name: str) -> None:
        """Erase every entry of file ``name`` (case-insensitive) — FR-174, DR-050.

        A no-op when the file is absent. The freed blocks become available to a
        later :meth:`write_file`.

        Satisfies: FR-174, DR-050.
        """
        target = name.strip().upper()
        self._erase(lambda u, b, e: (f"{b}.{e}" if e else b) == target)

    def save(self, path: str | Path | None = None) -> None:
        """Serialise the current image buffer to ``path`` (FR-174, DR-050).

        A path is required — a :class:`CpmImage` is built from bytes and carries no
        source path of its own, so the caller supplies the destination (the GUI
        always writes to a new Save-As path, never the source).

        Satisfies: FR-174, DR-050.
        """
        if path is None:
            raise ValueError("save() requires a destination path")
        Path(path).write_bytes(bytes(self._raw))
