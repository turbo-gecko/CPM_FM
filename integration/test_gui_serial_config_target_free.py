"""Target-free real-widget Serial Config workflows (MT-P*)."""

from __future__ import annotations

import pytest

from cpm_fm.utils import i18n


def _action(win, key: str):
    """Return the translated QAction registered for ``key``."""
    from PySide6.QtGui import QAction

    text = i18n.tr(key)
    return next(action for action in win.findChildren(QAction) if action.text() == text)


@pytest.mark.gui_integration
@pytest.mark.mt("MT-P02", "FR-020", "UIR-020", "UIR-021", "UIR-029")
def test_serial_config_action_opens_modal_grouped_two_column_dialog(
    gui_no_target, monkeypatch, qapp
):
    """The Serial menu opens the required modal two-group form.

    Verifies: FR-020, UIR-020, UIR-021, UIR-029.
    """
    from PySide6.QtWidgets import QDialog, QFormLayout, QGroupBox

    observed: dict[str, object] = {}

    def inspect_dialog(dialog):
        dialog.show()
        qapp.processEvents()
        groups = dialog.findChildren(QGroupBox)
        observed.update(
            title=dialog.windowTitle(),
            modal=dialog.isModal(),
            group_titles=[group.title() for group in groups],
            group_layouts=[group.layout() for group in groups],
        )
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.serial.tools.list_ports.comports",
        lambda: [],
    )
    monkeypatch.setattr(QDialog, "exec", inspect_dialog)

    _action(gui_no_target, "menu.config.serial").trigger()
    qapp.processEvents()

    assert observed["title"] == i18n.tr("config.serial.title")
    assert observed["modal"] is True
    assert observed["group_titles"] == [
        i18n.tr("config.serial.port_settings"),
        i18n.tr("config.serial.transmit_delay"),
    ]
    layouts = observed["group_layouts"]
    assert all(isinstance(layout, QFormLayout) for layout in layouts)
    assert all(
        all(
            layout.itemAt(row, QFormLayout.ItemRole.LabelRole) is not None
            and layout.itemAt(row, QFormLayout.ItemRole.FieldRole) is not None
            for row in range(layout.rowCount())
        )
        for layout in layouts
    )


@pytest.mark.gui_integration
@pytest.mark.mt("MT-P03", "UIR-024", "UIR-025", "UIR-026", "UIR-027", "UIR-028")
def test_serial_config_dropdowns_have_exact_options_and_defaults(gui_no_target, monkeypatch, qapp):
    """Serial option lists and unconfigured defaults match the specification.

    Verifies: UIR-024, UIR-025, UIR-026, UIR-027, UIR-028.
    """
    from PySide6.QtWidgets import QDialog

    captured: dict[str, object] = {}

    def capture_dialog(dialog):
        captured["dialog"] = dialog
        return QDialog.Rejected

    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.serial.tools.list_ports.comports",
        lambda: [],
    )
    monkeypatch.setattr(QDialog, "exec", capture_dialog)

    _action(gui_no_target, "menu.config.serial").trigger()
    dialog = captured["dialog"]

    expected = {
        "speed": (
            [
                "300",
                "1200",
                "2400",
                "4800",
                "9600",
                "14400",
                "19200",
                "38400",
                "57600",
                "115200",
                "230400",
                "460800",
                "921600",
            ],
            "115200",
        ),
        "data": (["7", "8"], "8"),
        "parity": (["NONE", "ODD", "EVEN", "MARK", "SPACE"], "NONE"),
        "stopbits": (["1", "2"], "1"),
        "flow": (["NONE", "XON/XOFF", "RTS/CTS", "DSR/DTR"], "RTS/CTS"),
    }
    for key, (options, default) in expected.items():
        combo = dialog.entries[key]
        assert [combo.itemText(index) for index in range(combo.count())] == options
        assert combo.currentText() == default


@pytest.mark.gui_integration
@pytest.mark.mt("MT-P04", "UIR-030", "UIR-031")
def test_serial_delay_fields_enforce_integer_0_to_255(gui_no_target, monkeypatch, qapp):
    """Both transmit-delay fields default to zero and reject invalid input.

    Verifies: UIR-030, UIR-031.
    """
    from PySide6.QtGui import QValidator
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog

    captured: dict[str, object] = {}

    def capture_dialog(dialog):
        captured["dialog"] = dialog
        return QDialog.Rejected

    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.serial.tools.list_ports.comports",
        lambda: [],
    )
    monkeypatch.setattr(QDialog, "exec", capture_dialog)

    _action(gui_no_target, "menu.config.serial").trigger()
    dialog = captured["dialog"]

    for key in ("msec_char", "msec_line"):
        edit = dialog.entries[key]
        validator = edit.validator()
        assert edit.text() == "0"
        assert validator.bottom() == 0
        assert validator.top() == 255
        for value in ("0", "1", "254", "255"):
            assert validator.validate(value, len(value))[0] == QValidator.State.Acceptable
        for value in ("-1", "abc", "1.5"):
            assert validator.validate(value, len(value))[0] == QValidator.State.Invalid
        assert validator.validate("256", 3)[0] != QValidator.State.Acceptable

        edit.clear()
        QTest.keyClicks(edit, "255")
        assert edit.text() == "255"
        edit.clear()
        QTest.keyClicks(edit, "abc")
        assert edit.text() == ""
        QTest.keyClicks(edit, "256")
        assert edit.text() != "256"


@pytest.mark.gui_integration
@pytest.mark.mt("MT-P06", "IFR-002")
def test_same_terminal_and_transport_port_saves_and_reopens(
    gui_no_target, monkeypatch, tmp_path, qapp
):
    """One physical port may back both logical ports and round-trip to JSON.

    Verifies: IFR-002.
    """
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog, QPushButton

    win = gui_no_target
    config_path = tmp_path / "shared-port.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_port": "COM1",
                "transport_port": "COM2",
                "unrelated_setting": "preserved",
            }
        ),
        encoding="utf-8",
    )
    win.load_config(str(config_path))

    def select_ports(_infos, show_all=False, always_include=()):
        del show_all
        return list(dict.fromkeys(["COM7", "COM8", *always_include]))

    monkeypatch.setattr("cpm_fm.gui.mw_config.select_ports", select_ports)
    monkeypatch.setattr(
        "cpm_fm.gui.mw_config.serial.tools.list_ports.comports",
        lambda: [],
    )

    openings: list[tuple[str, str]] = []

    def use_dialog(dialog):
        terminal = dialog.entries["terminal_port"]
        transport = dialog.entries["transport_port"]
        if not openings:
            assert terminal is not transport
            terminal.setCurrentText("COM7")
            transport.setCurrentText("COM7")
            save_button = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == i18n.tr("button.save")
            )
            QTest.mouseClick(save_button, Qt.MouseButton.LeftButton)
        openings.append((terminal.currentText(), transport.currentText()))
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", use_dialog)
    serial_action = _action(win, "menu.config.serial")
    serial_action.trigger()
    qapp.processEvents()

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["terminal_port"] == "COM7"
    assert saved["transport_port"] == "COM7"
    assert saved["unrelated_setting"] == "preserved"
    assert win.settings["terminal_port"] == "COM7"
    assert win.settings["transport_port"] == "COM7"

    serial_action.trigger()
    qapp.processEvents()
    assert openings == [("COM7", "COM7"), ("COM7", "COM7")]
