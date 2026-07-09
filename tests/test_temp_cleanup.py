"""Unit tests for the temporary-directory helper (cpm_fm.utils.temp_cleanup).

These exercise the shared-prefix temp-directory creation and the exit/start-up
sweep without a running Qt application (CR-014): a created directory uses the
shared prefix, the sweep removes both freshly created and historical (previous
session) directories, it leaves unrelated temp entries and stray prefix-matching
files alone, and a directory it cannot remove does not abort the sweep.

Satisfies: FR-016, FR-113a, FR-171.
"""

from __future__ import annotations

import os

from cpm_fm.utils import temp_cleanup
from cpm_fm.utils.temp_cleanup import TEMP_PREFIX, make_temp_dir, sweep_temp_dirs


def _point_tempdir_at(monkeypatch, path):
    """Redirect tempfile.gettempdir() so a test's sweep stays inside tmp_path."""
    monkeypatch.setattr(temp_cleanup.tempfile, "gettempdir", lambda: str(path))


def test_make_temp_dir_uses_shared_prefix(monkeypatch, tmp_path):
    """Verifies: FR-113a, FR-171."""
    _point_tempdir_at(monkeypatch, tmp_path)
    workdir = make_temp_dir()
    assert os.path.isdir(workdir)
    assert os.path.basename(workdir).startswith(TEMP_PREFIX)


def test_make_temp_dir_folds_in_tag(monkeypatch, tmp_path):
    """Verifies: FR-171."""
    _point_tempdir_at(monkeypatch, tmp_path)
    workdir = make_temp_dir("img_")
    # The disk-image workdir tag lives under the one shared prefix so it is swept
    # together with the untagged remote-view folders.
    assert os.path.basename(workdir).startswith(f"{TEMP_PREFIX}img_")


def test_sweep_removes_current_and_historical_dirs(monkeypatch, tmp_path):
    """Verifies: FR-016."""
    _point_tempdir_at(monkeypatch, tmp_path)
    # A directory created this "session" and one simulating a previous session's
    # orphan (both prefixed, one with content) must both go.
    current = make_temp_dir()
    historical = tmp_path / f"{TEMP_PREFIX}img_old"
    historical.mkdir()
    (historical / "LEFTOVER.TXT").write_text("stale")

    removed = sweep_temp_dirs()

    assert removed == 2
    assert not os.path.exists(current)
    assert not historical.exists()


def test_sweep_leaves_unrelated_entries(monkeypatch, tmp_path):
    """Verifies: FR-016."""
    _point_tempdir_at(monkeypatch, tmp_path)
    other_dir = tmp_path / "unrelated_dir"
    other_dir.mkdir()
    # A stray *file* sharing the prefix is not a working directory and is left be.
    stray_file = tmp_path / f"{TEMP_PREFIX}note.txt"
    stray_file.write_text("keep me")

    sweep_temp_dirs()

    assert other_dir.exists()
    assert stray_file.exists()


def test_sweep_tolerates_unremovable_dir(monkeypatch, tmp_path):
    """Verifies: FR-016."""
    _point_tempdir_at(monkeypatch, tmp_path)
    locked = make_temp_dir()
    removable = make_temp_dir()

    # Simulate a directory still held open (rmtree fails on it) — the sweep must
    # skip it without raising and still remove the others.
    real_rmtree = temp_cleanup.shutil.rmtree

    def fake_rmtree(path, *args, **kwargs):
        if path == locked:
            return  # ignore_errors semantics: leaves the tree in place
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(temp_cleanup.shutil, "rmtree", fake_rmtree)

    removed = sweep_temp_dirs()

    assert os.path.exists(locked)  # skipped, reclaimed by a later sweep
    assert not os.path.exists(removable)
    assert removed == 1
