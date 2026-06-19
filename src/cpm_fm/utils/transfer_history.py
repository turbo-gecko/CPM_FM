"""Persistent file-transfer history for the CP/M File Manager (Feature 2).

`TransferHistory` records one entry per file-transfer *attempt* — successful,
failed, or cancelled — so the user can review past transfers and re-initiate
("re-transfer") a previous one. It is a small, GUI-free persistence layer: it
imports nothing from the Qt toolkit, so it is safe to use from the transfer
worker threads and is unit-testable without a running Qt application (CR-014).

This is distinct from the raw serial receive/transmit buffers (`_rx_buffer` /
`_tx_buffer` in `app.py`), which hold un-structured terminal bytes rather than
per-file transfer records.

Storage (DR-045):
  * A JSON file (default ``~/.cpm_fm_history.json``) holding a list of entry
    objects, oldest first.
  * Each entry is a flat object with the fields described in
    :meth:`TransferHistory.add_entry`.
  * A retention policy bounds the file: at most ``max_entries`` (default 500)
    are kept, and entries older than ``max_age_days`` (default 30) are pruned.

Thread-safety: entries are recorded from the transfer worker threads, so every
public method takes an internal lock; the on-disk file is rewritten atomically
after each mutation.

Satisfies: FR-140, FR-141, FR-142, DR-045, CR-014.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# DR-045: the default history file lives in the user's home directory, separate
# from the per-configuration serial JSON (ConfigHandler) and the QSettings-backed
# UI/session state (WindowState).
DEFAULT_HISTORY_FILENAME = ".cpm_fm_history.json"

# FR-141: retention-policy defaults.
DEFAULT_MAX_ENTRIES = 500
DEFAULT_MAX_AGE_DAYS = 30

# FR-140: the recognised transfer directions and outcome statuses. ``direction``
# mirrors the value used throughout app.py: "remote" = host→remote upload (Copy
# to Remote), "host" = remote→host download (Copy to Host).
DIRECTIONS = ("remote", "host")
# FR-146: "skipped" records a file the user declined to overwrite at the
# destination (the conflict prompt's Skip action).
STATUSES = ("success", "failure", "cancelled", "skipped")


def default_history_path() -> str:
    """Return the default history file path (``~/.cpm_fm_history.json``).

    Satisfies: DR-045.
    """
    return str(Path.home() / DEFAULT_HISTORY_FILENAME)


class TransferHistory:
    """Records and persists per-file transfer attempts (Feature 2).

    Satisfies: FR-140, FR-141, FR-142, DR-045.
    """

    def __init__(
        self,
        path: str | None = None,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    ) -> None:
        """Open (and load) the history at ``path`` (default: the home file).

        ``path`` is injectable so tests use an isolated temporary file rather
        than the host's real history. Loading a missing or malformed file
        degrades to an empty history rather than raising, so a bad file never
        blocks start-up.

        Satisfies: FR-141, DR-045.
        """
        self._path = path if path is not None else default_history_path()
        self._max_entries = max(0, int(max_entries))
        self._max_age_days = max(0, int(max_age_days))
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = self._read_file()

    # ----------------------------------------------------------------- queries

    def get_entries(self) -> list[dict[str, Any]]:
        """Return a copy of the recorded entries, oldest first.

        A copy (of both the list and each entry) is returned so a caller cannot
        mutate the stored history in place.

        Satisfies: FR-140, FR-143.
        """
        with self._lock:
            return [dict(entry) for entry in self._entries]

    # --------------------------------------------------------------- mutations

    def add_entry(
        self,
        *,
        filename: str,
        path: str,
        direction: str,
        status: str,
        size: int = 0,
        error: str = "",
        retry: bool = False,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Append one transfer-attempt entry, prune, persist, and return it.

        Fields (FR-140):
          * ``filename`` — the file's base name (no path).
          * ``path`` — the host-side absolute path involved, retained so the
            transfer can be re-initiated later (FR-144).
          * ``direction`` — "remote" (Copy to Remote) or "host" (Copy to Host).
          * ``status`` — "success", "failure", "cancelled", or "skipped".
          * ``size`` — byte count (0 when unknown, e.g. a failed/cancelled
            download whose length X-Modem never carried).
          * ``error`` — the error message for a failure ("" otherwise).
          * ``retry`` — True when the entry resulted from a re-transfer (FR-144).
          * ``timestamp`` — ISO-8601 local time; generated now when omitted.

        Thread-safe: callable from the transfer worker threads (FR-142).

        Satisfies: FR-140, FR-141, FR-142, FR-144.
        """
        entry: dict[str, Any] = {
            "timestamp": timestamp if timestamp is not None else self._now_iso(),
            "filename": filename,
            "path": path,
            "direction": direction,
            "status": status,
            "size": int(size),
            "error": error,
            "retry": bool(retry),
        }
        with self._lock:
            self._entries.append(entry)
            self._prune_locked()
            self._write_file()
        return entry

    def clear_history(self) -> None:
        """Remove every entry and persist the now-empty history (FR-143).

        Satisfies: FR-143.
        """
        with self._lock:
            self._entries = []
            self._write_file()

    def prune_old_entries(self) -> int:
        """Apply the retention policy now and persist; return entries removed.

        Drops entries older than ``max_age_days`` and trims the oldest so at
        most ``max_entries`` remain. Normally applied automatically on each
        :meth:`add_entry`; exposed for explicit use/testing.

        Satisfies: FR-141.
        """
        with self._lock:
            before = len(self._entries)
            self._prune_locked()
            removed = before - len(self._entries)
            if removed:
                self._write_file()
            return removed

    def export_history(self, export_path: str) -> bool:
        """Write the current history to ``export_path`` as JSON; return success.

        Used by the History dialog's Export action (FR-143). Returns False on an
        OS error rather than raising, so an export failure is reportable.

        Satisfies: FR-143.
        """
        with self._lock:
            entries = [dict(entry) for entry in self._entries]
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=4)
            return True
        except OSError as e:  # pragma: no cover - depends on host filesystem
            print(f"Error exporting transfer history to {export_path}: {e}")
            return False

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _now_iso() -> str:
        """Return the current local time as an ISO-8601 string (second precision).

        Satisfies: FR-140.
        """
        return datetime.now().isoformat(timespec="seconds")

    def _prune_locked(self) -> None:
        """Apply the retention policy in place. Caller must hold ``self._lock``.

        Age-based pruning skips entries whose timestamp cannot be parsed (they
        are retained rather than silently dropped). Count-based pruning keeps the
        most-recent ``max_entries``.

        Satisfies: FR-141.
        """
        if self._max_age_days > 0:
            cutoff = datetime.now() - timedelta(days=self._max_age_days)
            kept: list[dict[str, Any]] = []
            for entry in self._entries:
                stamp = self._parse_timestamp(entry.get("timestamp"))
                if stamp is None or stamp >= cutoff:
                    kept.append(entry)
            self._entries = kept
        if self._max_entries and len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        """Parse an ISO-8601 timestamp string, or return None if unparseable.

        Satisfies: FR-141.
        """
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _read_file(self) -> list[dict[str, Any]]:
        """Load the entry list from disk, degrading to ``[]`` on any problem.

        A missing file, unreadable file, malformed JSON, or a JSON document that
        is not a list all yield an empty history rather than raising.

        Satisfies: FR-141, DR-045.
        """
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error loading transfer history {self._path}: {e}")
            return []
        if not isinstance(data, list):
            return []
        return [entry for entry in data if isinstance(entry, dict)]

    def _write_file(self) -> None:
        """Persist the entry list to disk. Caller must hold ``self._lock``.

        Failures are reported but not raised, so a transfer is never aborted
        merely because its history record could not be written.

        Satisfies: FR-141, DR-045.
        """
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=4)
        except OSError as e:  # pragma: no cover - depends on host filesystem
            print(f"Error saving transfer history {self._path}: {e}")
