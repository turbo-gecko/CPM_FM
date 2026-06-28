"""Drive the real ``MainWindow`` offscreen over a real serial link (plan §5).

Boots the actual ``MainWindow`` under ``QT_QPA_PLATFORM=offscreen`` (the same
pattern as ``tests/test_gui_smoke.py``) but with a **real** ``SerialManager`` and
the **working-copy** settings file, then exposes ``QTest``-based helpers to click
toolbar buttons, select list rows, and pump the Qt event loop until a real
worker-thread signal arrives (``process_until``).
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from cpm_fm.app import MainWindow

from .trace import get_logger, step

log = get_logger("gui")


class GuiDriver:
    """Thin driver around a live, offscreen ``MainWindow``."""

    def __init__(self, win: MainWindow, app: QApplication):
        self.win = win
        self.app = app
        self.probe_result: tuple[str, str | None] | None = None
        win.connect_probe_ok.connect(self._on_probe_ok)
        win.connect_probe_failed.connect(self._on_probe_failed)

    # ----- event pumping ---------------------------------------------------

    def _on_probe_ok(self, drive: str) -> None:
        self.probe_result = ("ok", drive)

    def _on_probe_failed(self) -> None:
        self.probe_result = ("failed", None)

    def pump(self, iterations: int = 5) -> None:
        for _ in range(iterations):
            self.app.processEvents()

    def process_until(self, predicate, timeout: float = 20.0, interval: float = 0.02) -> bool:
        """Pump Qt events until ``predicate()`` is true or ``timeout`` elapses."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(interval)
        self.app.processEvents()
        if predicate():
            return True
        log.warning("process_until timed out after %.0fs (condition never met)", timeout)
        return False

    # App background work runs on daemon threads named "Thread-N (<func>)". A
    # worker that outlives the window emits a queued signal on the (deleted)
    # QObject — a heap-corrupting crash — so every action quiesces these before
    # returning. The post-connect probe in particular chains into a remote-list
    # refresh thread that must finish before teardown.
    _WORKER_HINTS = ("_do_", "_logic", "_batch", "_transfer", "probe", "boot", "backup", "restore")

    def _workers_alive(self) -> list[str]:
        """Names of app worker threads matching the daemon-worker hints."""
        return [
            t.name for t in threading.enumerate() if any(h in t.name for h in self._WORKER_HINTS)
        ]

    def quiesce(self, timeout: float = 15.0) -> bool:
        """Pump events until no app worker thread is still running.

        A finishing worker often queues a signal that *chains* into the next
        worker on the GUI thread — e.g. ``_transfer_to_remote_batch`` emits
        ``transfer_completed`` as it dies, whose handler calls
        ``refresh_remote_files`` and spawns a fresh listing thread. So observing
        "no worker alive" once is not enough: we pump events (to run the queued
        signal and let any chained worker start), settle briefly, and only
        declare quiescent if *still* idle — otherwise we keep waiting. Without
        this, ``quiesce`` can return in the gap and the test reads a stale list.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()
            if not self._workers_alive():
                self.app.processEvents()  # run any queued chaining signal
                time.sleep(0.1)
                self.app.processEvents()  # let a chained worker register/start
                if not self._workers_alive():
                    return True
                continue  # a chained worker started — keep waiting for it
            time.sleep(0.02)
        log.warning(
            "quiesce timed out after %.0fs — worker thread(s) still alive: %s",
            timeout,
            self._workers_alive(),
        )
        return False

    # ----- connection ------------------------------------------------------

    def connect(self, timeout: float = 25.0) -> tuple[str, str | None] | None:
        """Connect over real serial and wait for the post-connect probe.

        Returns the probe result ``("ok", drive)`` / ``("failed", None)`` or
        ``None`` if the terminal port never opened.
        """
        step(log, "GUI connect…")
        self.probe_result = None
        self.win.do_connect()
        self.process_until(
            lambda: self.probe_result is not None or not self.win.serial_mgr.terminal_connected,
            timeout,
        )
        # The probe-ok handler chains into a remote-list refresh worker; wait for
        # it (and any other worker) to finish so it can't fire on a dead window.
        self.quiesce()
        if self.probe_result and self.probe_result[0] == "ok":
            step(log, "probe = ok (drive %s:)", self.probe_result[1])
        else:
            step(log, "probe = %s", self.probe_result)
        return self.probe_result

    def disconnect(self) -> None:
        step(log, "GUI disconnect")
        self.win.do_disconnect()
        self.quiesce()

    @property
    def connected(self) -> bool:
        return self.win.serial_mgr.terminal_connected

    @property
    def transport_connected(self) -> bool:
        return self.win.serial_mgr.transport_connected

    # ----- list inspection / selection ------------------------------------

    def remote_names(self) -> list[str]:
        lst = self.win.remote_list
        return [lst.item(i).text() for i in range(lst.count())]

    def host_names(self) -> list[str]:
        lst = self.win.host_list
        return [lst.item(i).text() for i in range(lst.count())]

    def _select(self, list_widget, names: list[str]) -> None:
        wanted = {n.upper() for n in names}
        list_widget.clearSelection()
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.text().upper() in wanted:
                item.setSelected(True)
        self.pump()

    def select_remote(self, names: list[str]) -> None:
        step(log, "select remote %s", names)
        self._select(self.win.remote_list, names)

    def select_host(self, names: list[str]) -> None:
        step(log, "select host %s", names)
        self._select(self.win.host_list, names)

    # ----- buttons / actions ----------------------------------------------

    def click_button(self, group, text: str) -> None:
        """Left-click the push button labelled ``text`` within ``group``."""
        step(log, "click %r", text)
        btn = next(b for b in group.findChildren(QPushButton) if b.text() == text)
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        self.pump()

    # ----- higher-level flows ---------------------------------------------

    def refresh_host(self) -> None:
        step(log, "refresh host files")
        self.win.refresh_host_files()
        self.quiesce()

    def upload(self, names: list[str]) -> None:
        """Select host files and Copy to Remote (real worker thread)."""
        step(log, "upload %s", names)
        self.refresh_host()
        self.select_host(names)
        self.win.do_copy_to_remote()
        self.quiesce()

    def download(self, names: list[str]) -> None:
        """Select remote files and Copy to Host (real worker thread)."""
        step(log, "download %s", names)
        self.select_remote(names)
        self.win.do_copy_to_host()
        self.quiesce()

    def refresh_remote(self) -> None:
        step(log, "refresh remote files")
        self.win.refresh_remote_files()
        self.quiesce()

    def set_drive(self, letter: str) -> None:
        """Select ``letter`` in the remote drive drop-down (fires change_drive)."""
        step(log, "set drive %s:", letter)
        combo = self.win.drive_combo
        idx = combo.findText(f"{letter}:")
        assert idx >= 0, f"drive {letter}: not in combo"
        combo.setCurrentIndex(idx)
        self.pump()
