"""Pytest plugin for the cpm-fm HIL integration harness.

Provides:
- the ``--target`` / ``--all-targets`` / ``--run-destructive`` CLI options,
- target parametrisation of the ``target`` fixture (so the whole suite re-runs
  per selected hardware, labelled ``...[rc2014]``),
- marker registration + auto-skip gating (``hil``/``two_port``/``destructive``/
  ``visual``/``best_effort``),
- the fresh settings working-copy fixture with the original-immutability guard,
- the results plugin that writes per-run artifacts + the committed ledger.

Run with ``pytest integration/`` (this directory's ``pytest.ini`` is a separate,
explicit invocation; the default root ``pytest`` only collects ``tests/``).
"""

from __future__ import annotations

import os

# GUI phases construct the real MainWindow; force the offscreen Qt platform the
# same way tests/test_gui_smoke.py does, before any PySide6 import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from helpers.config import HilConfigError, load_hil_config, resolve_targets
from helpers.ids import mt_info
from helpers.results import ResultsRecorder
from helpers.settings_copy import file_sha256, make_working_copy

# --------------------------------------------------------------------------- #
# Options & configuration
# --------------------------------------------------------------------------- #


def pytest_addoption(parser):
    group = parser.getgroup("hil", "cpm-fm hardware-in-the-loop harness")
    group.addoption(
        "--target",
        action="append",
        default=[],
        metavar="NAME",
        help="run against this registered target (repeatable)",
    )
    group.addoption(
        "--all-targets",
        action="store_true",
        default=False,
        help="run against every registered target in turn",
    )
    group.addoption(
        "--run-destructive",
        action="store_true",
        default=False,
        help="enable destructive tests (backup/restore wipes of the scratch drive)",
    )


def pytest_configure(config):
    for name, desc in [
        ("hil", "requires a live CP/M peer on the bench"),
        ("two_port", "requires a target with distinct Terminal/Transport ports"),
        ("destructive", "erases the scratch drive; needs --run-destructive"),
        ("visual", "widget-tree/look-and-feel assertion, no peer required"),
        ("best_effort", "hardware/timing-dependent; may end Blocked"),
        ("mt", 'MT-ID + requirement tagging: @pytest.mark.mt("MT-T03", "FR-081")'),
    ]:
        config.addinivalue_line("markers", f"{name}: {desc}")

    # Resolve the selected targets once. A missing/empty hil_config is not a hard
    # error here — hil-marked tests auto-skip with a clear reason instead.
    config._hil_targets = []
    config._hil_error = None
    try:
        cfg = load_hil_config()
        config._hil_targets = resolve_targets(
            cfg,
            names=config.getoption("--target") or None,
            all_targets=config.getoption("--all-targets"),
        )
    except HilConfigError as e:
        config._hil_error = str(e)

    config._hil_recorder = ResultsRecorder(
        targets=config._hil_targets,
        flags={
            "target": config.getoption("--target"),
            "all_targets": config.getoption("--all-targets"),
            "run_destructive": config.getoption("--run-destructive"),
        },
    )


def pytest_generate_tests(metafunc):
    """Parametrise the ``target`` fixture over the selected hardware target(s)."""
    if "target" not in metafunc.fixturenames:
        return
    targets = metafunc.config._hil_targets
    if not targets:
        reason = metafunc.config._hil_error or "no HIL target/config available"
        metafunc.parametrize(
            "target",
            [pytest.param(None, marks=pytest.mark.skip(reason=reason), id="no-target")],
            scope="session",
        )
        return
    metafunc.parametrize(
        "target",
        targets,
        ids=[t.name for t in targets],
        scope="session",
    )


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _hil_gate(request):
    """Auto-skip hardware/destructive/two-port cases when not applicable."""
    item = request.node
    if item.get_closest_marker("visual"):
        return  # no peer required, always runnable
    needs_target = any(item.get_closest_marker(m) for m in ("hil", "two_port", "destructive"))
    if not needs_target:
        return
    target = request.getfixturevalue("target")
    if target is None:
        pytest.skip(request.config._hil_error or "no HIL target/config available")
    if item.get_closest_marker("two_port") and not target.two_port:
        pytest.skip(f"target {target.name!r} is single-port (two_port=false)")
    if item.get_closest_marker("destructive"):
        if not request.config.getoption("--run-destructive"):
            pytest.skip("destructive tests require --run-destructive")
        if not target.scratch_drive:
            pytest.skip(f"target {target.name!r} defines no scratch_drive")
        # Safety: the disposable scratch drive must differ from the declared
        # protected home drive, or a real data drive could be wiped.
        if target.connect_drive and (target.scratch_drive.upper() == target.connect_drive.upper()):
            pytest.skip(
                f"scratch_drive {target.scratch_drive!r} equals the protected "
                f"connect_drive {target.connect_drive!r} — refusing destructive run"
            )


# --------------------------------------------------------------------------- #
# Settings working-copy fixture (plan §2.1)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def peer(target):
    """A connected :class:`CpmPeer` for the target, shared across a test module.

    Scoped per *module* rather than per session because the common single-port
    bench rig (terminal == transport) can only be held by one ``SerialManager``
    at a time: the GUI tier opens the same physical port through the real
    ``MainWindow``, so the protocol-tier peer must release it when its module
    ends. The peer reads ports/commands from the parsed settings and never
    writes the settings file (the immutability guard covers the app/GUI paths).
    """
    if target is None:
        pytest.skip("no HIL target/config available")
    from helpers.peer import CpmPeer, PeerError

    p = CpmPeer(target.load_settings())
    try:
        p.connect()
    except PeerError as e:
        pytest.skip(f"BLOCKED: could not connect to target {target.name!r}: {e}")
    yield p
    p.close()


@pytest.fixture
def scratch_drive(target):
    """The disposable scratch drive letter, skipping when none is configured."""
    if target is None or not target.scratch_drive:
        pytest.skip("no scratch_drive configured for this target")
    return target.scratch_drive


@pytest.fixture(scope="session")
def qapp():
    """A process-wide ``QApplication`` for the GUI tier (offscreen)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def gui(target, qapp, settings_copy, tmp_path):
    """A live, offscreen ``MainWindow`` loaded with the working-copy settings.

    Isolated ``WindowState`` (temp INI) and ``TransferHistory`` (temp file) so
    tests never touch the host's real QSettings or ``~/.cpm_fm_history.json``.
    Disconnects and tears the window down at the end so the next test (and the
    shared serial port) start clean.
    """
    if target is None:
        pytest.skip("no HIL target/config available")

    from helpers.gui_driver import GuiDriver
    from PySide6.QtCore import QSettings

    from cpm_fm.app import MainWindow
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.utils import i18n
    from cpm_fm.utils.transfer_history import TransferHistory

    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    state = WindowState(QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat))
    history = TransferHistory(str(tmp_path / "history.json"))
    win = MainWindow(state, history)
    win.load_config(str(settings_copy))
    # Point the Host Files pane at a throwaway temp dir so host-side file
    # create/rename/delete never touch the operator's real host_directory.
    host_dir = tmp_path / "host"
    host_dir.mkdir(exist_ok=True)
    win.host_dir = str(host_dir)
    driver = GuiDriver(win, qapp)
    try:
        yield driver
    finally:
        # Order matters: detach the read callback FIRST so a late delivery from
        # the daemon serial read thread cannot call into a half-destroyed
        # QObject (a hard segfault), then stop the thread and close ports before
        # the window is torn down.
        import time as _time

        # Drain any in-flight app worker threads BEFORE deleting the window, so a
        # queued signal can never fire on a freed QObject (heap corruption).
        driver.quiesce()
        win.serial_mgr.on_data_received = None
        win.serial_mgr.close_ports()  # stops + joins the read thread, closes ports
        win.close()
        win.deleteLater()
        qapp.processEvents()
        # Let Windows fully release the (single shared) COM port before reopen.
        _time.sleep(0.5)
        i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture
def vwin(qapp, tmp_path):
    """A built-but-unconnected ``MainWindow`` for visual/widget-tree assertions.

    No serial port is opened (no peer needed), so this fixture is independent of
    any HIL target — it backs the ``visual`` tier (plan §6). The Material theme
    is applied to the application so stylesheet/theme assertions are meaningful.
    """
    from PySide6.QtCore import QSettings

    from cpm_fm.app import MainWindow
    from cpm_fm.gui.theme import apply_theme
    from cpm_fm.gui.window_state import WindowState
    from cpm_fm.utils import i18n
    from cpm_fm.utils.transfer_history import TransferHistory

    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    apply_theme(qapp)
    state = WindowState(QSettings(str(tmp_path / "vstate.ini"), QSettings.Format.IniFormat))
    history = TransferHistory(str(tmp_path / "vhistory.json"))
    win = MainWindow(state, history)
    try:
        yield win
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()
        i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture
def settings_copy(target, tmp_path):
    """A fresh working copy of the target's app settings, per test.

    Yields the working-copy :class:`Path`. At teardown the original file's
    SHA-256 is asserted unchanged — a guard rail that fails the test if any
    mutation leaked back to the source file.
    """
    src = target.settings_path
    before = file_sha256(src)
    copy = make_working_copy(src, tmp_path)
    yield copy
    after = file_sha256(src)
    assert after == before, (
        f"original settings file {src} was modified during the test "
        f"(sha {before[:12]} -> {after[:12]})"
    )


# --------------------------------------------------------------------------- #
# Results plugin
# --------------------------------------------------------------------------- #


def _target_name_for(item) -> str:
    callspec = getattr(item, "callspec", None)
    if callspec is not None:
        tgt = callspec.params.get("target")
        if tgt is not None:
            return tgt.name
    return "_local"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    recorder = getattr(item.config, "_hil_recorder", None)
    if recorder is None:
        return
    if report.when == "setup":
        mt_id, reqs = mt_info(item)
        recorder.start_item(item.nodeid, mt_id, reqs, _target_name_for(item))
    recorder.add_report(report)


def pytest_sessionfinish(session, exitstatus):
    recorder = getattr(session.config, "_hil_recorder", None)
    if recorder is None:
        return
    written = recorder.finish()
    if written:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line("")
            for path in written:
                reporter.write_line(f"[hil] results written: {path}")
