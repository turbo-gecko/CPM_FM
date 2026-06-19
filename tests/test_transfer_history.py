"""Unit tests for the persistent transfer-history module (Feature 2).

These exercise the pure-Python `TransferHistory` without a running Qt
application (CR-014): the entry schema, JSON persistence round-trip, the
retention policy (count + age), thread-safe concurrent recording, export, and
graceful degradation on a missing/malformed file.

Satisfies: FR-140, FR-141, FR-142, FR-143, DR-045.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta

from cpm_fm.utils.transfer_history import STATUSES, TransferHistory


def _history(tmp_path, **kwargs):
    return TransferHistory(str(tmp_path / "history.json"), **kwargs)


def test_skipped_is_a_recognised_status(tmp_path):
    # FR-146: a file the user declined to overwrite is recorded as "skipped".
    assert "skipped" in STATUSES
    h = _history(tmp_path)
    entry = h.add_entry(
        filename="FOO.TXT", path="/host/FOO.TXT", direction="host", status="skipped"
    )
    assert entry["status"] == "skipped"
    assert h.get_entries()[0]["status"] == "skipped"


def test_add_entry_records_all_fields(tmp_path):
    # FR-140: an entry carries filename, path, direction, status, size, error,
    # retry, and a timestamp.
    h = _history(tmp_path)
    entry = h.add_entry(
        filename="FOO.TXT",
        path="/host/FOO.TXT",
        direction="remote",
        status="success",
        size=128,
        error="",
        retry=False,
    )
    assert entry["filename"] == "FOO.TXT"
    assert entry["path"] == "/host/FOO.TXT"
    assert entry["direction"] == "remote"
    assert entry["status"] == "success"
    assert entry["size"] == 128
    assert entry["error"] == ""
    assert entry["retry"] is False
    assert entry["timestamp"]  # non-empty ISO timestamp
    assert h.get_entries() == [entry]


def test_persistence_round_trip(tmp_path):
    # FR-141/DR-045: entries persist to JSON and reload in a fresh instance.
    h = _history(tmp_path)
    h.add_entry(filename="A.TXT", path="/h/A.TXT", direction="host", status="failure", error="boom")
    h.add_entry(filename="B.COM", path="/h/B.COM", direction="remote", status="success", size=256)

    reloaded = _history(tmp_path)
    entries = reloaded.get_entries()
    assert [e["filename"] for e in entries] == ["A.TXT", "B.COM"]
    assert entries[0]["error"] == "boom"
    assert entries[1]["size"] == 256


def test_get_entries_returns_copy(tmp_path):
    # FR-140: a caller cannot mutate the stored history via the returned list.
    h = _history(tmp_path)
    h.add_entry(filename="A.TXT", path="/h/A.TXT", direction="host", status="success")
    entries = h.get_entries()
    entries[0]["filename"] = "MUTATED"
    entries.append({"x": 1})
    assert [e["filename"] for e in h.get_entries()] == ["A.TXT"]


def test_clear_history(tmp_path):
    # FR-143: clearing empties the history and persists the empty list.
    h = _history(tmp_path)
    h.add_entry(filename="A.TXT", path="/h/A.TXT", direction="host", status="success")
    h.clear_history()
    assert h.get_entries() == []
    assert _history(tmp_path).get_entries() == []


def test_retention_trims_to_max_entries(tmp_path):
    # FR-141: only the most-recent max_entries are kept (oldest dropped first).
    h = _history(tmp_path, max_entries=3, max_age_days=0)
    for i in range(5):
        h.add_entry(filename=f"F{i}.TXT", path=f"/h/F{i}.TXT", direction="remote", status="success")
    names = [e["filename"] for e in h.get_entries()]
    assert names == ["F2.TXT", "F3.TXT", "F4.TXT"]


def test_retention_prunes_old_entries(tmp_path):
    # FR-141: entries older than max_age_days are pruned; recent ones are kept.
    h = _history(tmp_path, max_age_days=30)
    old = (datetime.now() - timedelta(days=40)).isoformat(timespec="seconds")
    recent = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    h.add_entry(
        filename="OLD.TXT", path="/h/OLD.TXT", direction="host", status="success", timestamp=old
    )
    h.add_entry(
        filename="NEW.TXT", path="/h/NEW.TXT", direction="host", status="success", timestamp=recent
    )
    names = [e["filename"] for e in h.get_entries()]
    assert names == ["NEW.TXT"]


def test_prune_keeps_unparseable_timestamps(tmp_path):
    # FR-141: an entry with an unparseable timestamp is retained, not dropped.
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps([{"filename": "X.TXT", "timestamp": "not-a-date", "direction": "host"}]),
        encoding="utf-8",
    )
    h = TransferHistory(str(path), max_age_days=30)
    h.prune_old_entries()
    assert [e["filename"] for e in h.get_entries()] == ["X.TXT"]


def test_missing_file_starts_empty(tmp_path):
    # FR-141/DR-045: a missing history file yields an empty history, no error.
    assert _history(tmp_path).get_entries() == []


def test_malformed_file_degrades_to_empty(tmp_path):
    # FR-141/DR-045: malformed JSON (or a non-list document) degrades to empty.
    path = tmp_path / "history.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    assert TransferHistory(str(path)).get_entries() == []
    path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert TransferHistory(str(path)).get_entries() == []


def test_export_history(tmp_path):
    # FR-143: export writes the current entries to a chosen JSON file.
    h = _history(tmp_path)
    h.add_entry(filename="A.TXT", path="/h/A.TXT", direction="host", status="success", size=10)
    export = tmp_path / "export.json"
    assert h.export_history(str(export)) is True
    data = json.loads(export.read_text(encoding="utf-8"))
    assert [e["filename"] for e in data] == ["A.TXT"]


def test_thread_safe_concurrent_add(tmp_path):
    # FR-142: concurrent recording from many threads loses no entries and never
    # corrupts the store.
    h = _history(tmp_path, max_entries=10_000, max_age_days=0)
    threads_count, per_thread = 8, 50

    def worker(tid):
        for i in range(per_thread):
            h.add_entry(
                filename=f"T{tid}_{i}.TXT",
                path=f"/h/T{tid}_{i}.TXT",
                direction="remote",
                status="success",
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(threads_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(h.get_entries()) == threads_count * per_thread
    # The persisted file is valid JSON with the same count.
    assert len(_history(tmp_path, max_entries=10_000).get_entries()) == threads_count * per_thread
