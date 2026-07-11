"""Debug-log file sink for the verbose transfer trace.

When the ``debug_logging`` setting is on, the application emits a verbose
X-Modem/transfer trace. Historically this went to standard output only, which is
invisible when the app runs under the ``cpm-fm`` launcher (bound to
``pythonw.exe``, no console); it was only visible when run as ``python -m
cpm_fm``. This module adds a file sink so the trace is captured regardless of how
the app is launched: it writes ``cpm_fm_debug.log`` in the executable's directory
for a frozen (PyInstaller) build, or in the current working directory (the folder
the app was launched from) for a source run.

The :class:`logging.FileHandler` is attached lazily, on the first call to
:func:`get_debug_logger`, so no (empty) log file is created when debug logging is
off. If the target folder is not writable the handler falls back to a
:class:`logging.NullHandler`, so logging never raises.

This module is pure host-side logic and imports nothing from the GUI toolkit
(CR-014), so it is unit-testable without a running Qt application.

Satisfies: FR-088, CR-014.
"""

from __future__ import annotations

import logging
import os
import sys

# Name of the shared debug logger and the log file it writes.
DEBUG_LOGGER_NAME = "cpm_fm.debug"
DEBUG_LOG_FILENAME = "cpm_fm_debug.log"


def debug_log_dir() -> str:
    """Return the folder the debug log file is written to (the app's own folder).

    A frozen (PyInstaller) build reports ``sys.frozen`` and runs from a bundled
    executable, so the log sits beside that executable
    (``dirname(sys.executable)``). A source/editable run (the ``cpm-fm``
    entry-point launcher, or ``python -m cpm_fm``) has no discoverable bundled
    executable — ``sys.executable`` points at the interpreter, not the generated
    ``cpm-fm.exe`` wrapper — so the log is written to the current working
    directory, i.e. the folder the application was launched from. That is where
    the user is looking for it.

    Satisfies: FR-088.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.getcwd()


def debug_log_path() -> str:
    """Full path of the debug log file within :func:`debug_log_dir`.

    Satisfies: FR-088.
    """
    return os.path.join(debug_log_dir(), DEBUG_LOG_FILENAME)


def get_debug_logger() -> logging.Logger:
    """Return the shared debug logger, attaching its file handler on first use.

    The :class:`logging.FileHandler` is created the first time this is called and
    reused thereafter (idempotent). Because callers only invoke this when the
    ``debug_logging`` setting is on and there is something to write, no empty log
    file is created while debug logging is off. A failure to open the log file
    (e.g. a read-only application folder) falls back to a
    :class:`logging.NullHandler` so debug logging degrades quietly rather than
    raising.

    Satisfies: FR-088.
    """
    logger = logging.getLogger(DEBUG_LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        # Keep the trace out of the root logger's handlers (e.g. the integration
        # suite's), so it only ever lands in this file.
        logger.propagate = False
        try:
            handler: logging.Handler = logging.FileHandler(debug_log_path(), encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        except OSError:
            handler = logging.NullHandler()
        logger.addHandler(handler)
    return logger
