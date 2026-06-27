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
        return bool(predicate())

    # App background work runs on daemon threads named "Thread-N (<func>)". A
    # worker that outlives the window emits a queued signal on the (deleted)
    # QObject — a heap-corrupting crash — so every action quiesces these before
    # returning. The post-connect probe in particular chains into a remote-list
    # refresh thread that must finish before teardown.
    _WORKER_HINTS = ("_do_", "_logic", "_batch", "_transfer", "probe", "boot", "backup", "restore")

    def quiesce(self, timeout: float = 15.0) -> bool:
        """Pump events until no app worker thread is still running."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()
            alive = [
                t for t in threading.enumerate() if any(h in t.name for h in self._WORKER_HINTS)
            ]
            if not alive:
                self.app.processEvents()
                return True
            time.sleep(0.02)
        return False

    # ----- connection ------------------------------------------------------

    def connect(self, timeout: float = 25.0) -> tuple[str, str | None] | None:
        """Connect over real serial and wait for the post-connect probe.

        Returns the probe result ``("ok", drive)`` / ``("failed", None)`` or
        ``None`` if the terminal port never opened.
        """
        self.probe_result = None
        self.win.do_connect()
        self.process_until(
            lambda: self.probe_result is not None or not self.win.serial_mgr.terminal_connected,
            timeout,
        )
        # The probe-ok handler chains into a remote-list refresh worker; wait for
        # it (and any other worker) to finish so it can't fire on a dead window.
        self.quiesce()
        return self.probe_result

    def disconnect(self) -> None:
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
        self._select(self.win.remote_list, names)

    def select_host(self, names: list[str]) -> None:
        self._select(self.win.host_list, names)

    # ----- buttons / actions ----------------------------------------------

    def click_button(self, group, text: str) -> None:
        """Left-click the push button labelled ``text`` within ``group``."""
        btn = next(b for b in group.findChildren(QPushButton) if b.text() == text)
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        self.pump()

    # ----- higher-level flows ---------------------------------------------

    def refresh_host(self) -> None:
        self.win.refresh_host_files()
        self.quiesce()

    def upload(self, names: list[str]) -> None:
        """Select host files and Copy to Remote (real worker thread)."""
        self.refresh_host()
        self.select_host(names)
        self.win.do_copy_to_remote()
        self.quiesce()

    def download(self, names: list[str]) -> None:
        """Select remote files and Copy to Host (real worker thread)."""
        self.select_remote(names)
        self.win.do_copy_to_host()
        self.quiesce()

    def refresh_remote(self) -> None:
        self.win.refresh_remote_files()
        self.quiesce()

    def set_drive(self, letter: str) -> None:
        """Select ``letter`` in the remote drive drop-down (fires change_drive)."""
        combo = self.win.drive_combo
        idx = combo.findText(f"{letter}:")
        assert idx >= 0, f"drive {letter}: not in combo"
        combo.setCurrentIndex(idx)
        self.pump()
