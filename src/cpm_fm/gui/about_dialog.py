from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from cpm_fm.gui.dialog_buttons import build_button_row
from cpm_fm.utils.i18n import tr
from cpm_fm.version import APP_NAME, REPO_URL, get_version


class AboutDialog(QDialog):
    """Modal About dialog (Help > About).

    Displays the program name, the application version (read from
    ``src/version.txt``, DR-040), a clickable hyperlink to the project's GitHub
    repository that opens in the host's default browser, and a single OK button
    (centred per UIR-075) that closes the dialog.

    Satisfies: FR-022, UIR-076.
    """

    def __init__(self, parent=None):
        """
        Satisfies: FR-022, UIR-076, UIR-075.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("about.title"))
        self.setModal(True)

        layout = QVBoxLayout(self)

        # UIR-076: program name.
        name_label = QLabel(APP_NAME)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        # UIR-076: application version (DR-040), shown as "Version <x.y.z>".
        version_label = QLabel(tr("about.version", version=get_version()))
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        # UIR-076: clickable hyperlink to the GitHub repository, opened in the
        # host's default browser.
        link_label = QLabel(f'<a href="{REPO_URL}">{REPO_URL}</a>')
        link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link_label.setOpenExternalLinks(True)
        link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(link_label)

        # UIR-076/UIR-075: a single OK button, centred, closes the dialog.
        ok_btn = QPushButton(tr("button.ok"))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        layout.addLayout(build_button_row(accept_button=ok_btn))
