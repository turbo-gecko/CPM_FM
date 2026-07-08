"""``CpmImage`` — a mounted raw-sector CP/M image bound to a geometry.

Owns the skew-aware sector reader that turns a data-area byte range into bytes,
and composes :mod:`directory` + :mod:`filesystem` to list and read files. Pure
``utils`` layer: no GUI imports (CR-014).

Satisfies: FR-169, FR-172, DR-049, CR-014.
"""

from __future__ import annotations

from pathlib import Path

from cpm_fm.utils.disk_image import filesystem
from cpm_fm.utils.disk_image.directory import CpmDirEntry, parse_directory
from cpm_fm.utils.disk_image.filesystem import CpmFileEntry
from cpm_fm.utils.disk_image.geometry import DiskDef, build_skew_table


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
        self._raw = raw
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

    # --- high-level API ------------------------------------------------------

    @property
    def entries(self) -> list[CpmDirEntry]:
        return self._dir_entries

    def list_files(self) -> list[CpmFileEntry]:
        """List the files on the image (FR-169).

        Satisfies: FR-169.
        """
        return filesystem.list_files(self._dir_entries, self.geom)

    def read_file(self, name: str) -> bytes:
        """Return the byte content of ``name`` ("NAME.EXT", case-insensitive) — FR-171.

        Satisfies: FR-171, DR-049.
        """
        return filesystem.read_file(self, self._dir_entries, name)

    # --- write path (deferred to the v2.28+ write feature group) -------------

    def write_file(self, name: str, data: bytes) -> None:
        raise NotImplementedError("image write support is a later feature group")

    def delete_file(self, name: str) -> None:
        raise NotImplementedError("image write support is a later feature group")

    def save(self, path: str | Path | None = None) -> None:
        raise NotImplementedError("image write support is a later feature group")
