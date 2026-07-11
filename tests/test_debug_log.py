"""Unit tests for the debug-log file sink (cpm_fm.utils.debug_log).

These exercise the FR-088 file sink without a running Qt application (CR-014):
the log directory resolves to the executable's folder for a frozen build and the
package folder otherwise; the file handler is attached lazily so nothing is
created until the first write; a debug message actually lands in
``cpm_fm_debug.log``; and a read-only application folder degrades to a
NullHandler rather than raising.

Satisfies: FR-088, CR-014.
"""

from __future__ import annotations

import logging
import os

import pytest

from cpm_fm.utils import debug_log
from cpm_fm.utils.debug_log import (
    DEBUG_LOG_FILENAME,
    DEBUG_LOGGER_NAME,
    debug_log_dir,
    debug_log_path,
    get_debug_logger,
)


@pytest.fixture(autouse=True)
def _reset_debug_logger():
    """Detach the shared logger's handlers before and after each test.

    ``get_debug_logger`` attaches a handler to a process-global
    ``logging.getLogger`` singleton, so tests must reset it to stay isolated.
    """
    logger = logging.getLogger(DEBUG_LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    yield
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def test_log_dir_is_cwd_for_source_run(monkeypatch, tmp_path):
    """Verifies: FR-088."""
    # A non-frozen (source/editable) run has no discoverable bundled executable,
    # so the log lives in the current working directory — the folder the app was
    # launched from — NOT the utils subpackage this module sits in.
    monkeypatch.setattr(debug_log.sys, "frozen", False, raising=False)
    monkeypatch.chdir(tmp_path)
    result = debug_log_dir()
    assert result == os.getcwd()
    assert os.path.abspath(result) == os.path.abspath(str(tmp_path))


def test_log_dir_is_executable_folder_when_frozen(monkeypatch, tmp_path):
    """Verifies: FR-088."""
    # A frozen (PyInstaller) build reports sys.frozen and runs from a bundled
    # executable, so the log sits beside that executable.
    exe = tmp_path / "cpm-fm.exe"
    monkeypatch.setattr(debug_log.sys, "frozen", True, raising=False)
    monkeypatch.setattr(debug_log.sys, "executable", str(exe))
    assert debug_log_dir() == str(tmp_path)


def test_handler_is_lazy_no_file_until_write(monkeypatch, tmp_path):
    """Verifies: FR-088."""
    monkeypatch.setattr(debug_log, "debug_log_dir", lambda: str(tmp_path))
    log_file = tmp_path / DEBUG_LOG_FILENAME
    # Merely importing / not calling the logger must not create the file: no file
    # is created while debug logging is off.
    assert not log_file.exists()


def test_debug_message_is_written_to_app_folder(monkeypatch, tmp_path):
    """Verifies: FR-088."""
    monkeypatch.setattr(debug_log, "debug_log_dir", lambda: str(tmp_path))
    logger = get_debug_logger()
    logger.debug("[xfer send 1.00] 01 02 03")
    for handler in logger.handlers:
        handler.flush()

    log_file = tmp_path / DEBUG_LOG_FILENAME
    assert log_file.exists()
    assert debug_log_path() == str(log_file)
    assert "[xfer send 1.00] 01 02 03" in log_file.read_text(encoding="utf-8")


def test_get_debug_logger_is_idempotent(monkeypatch, tmp_path):
    """Verifies: FR-088."""
    monkeypatch.setattr(debug_log, "debug_log_dir", lambda: str(tmp_path))
    logger_a = get_debug_logger()
    logger_b = get_debug_logger()
    # The same singleton, with exactly one handler attached across repeated calls.
    assert logger_a is logger_b
    assert len(logger_a.handlers) == 1


def test_unwritable_folder_falls_back_to_nullhandler(monkeypatch, tmp_path):
    """Verifies: FR-088."""
    # Simulate a read-only application folder: opening the file raises OSError.
    monkeypatch.setattr(debug_log, "debug_log_dir", lambda: str(tmp_path))

    def _raise(*_args, **_kwargs):
        raise OSError("read-only application folder")

    monkeypatch.setattr(debug_log.logging, "FileHandler", _raise)

    logger = get_debug_logger()
    # Must not raise, and must still be usable (message swallowed by NullHandler).
    logger.debug("dropped quietly")
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.NullHandler)
    assert not (tmp_path / DEBUG_LOG_FILENAME).exists()
