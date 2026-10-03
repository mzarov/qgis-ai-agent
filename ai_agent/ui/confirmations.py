"""The modal questions the agent asks before it shares data or runs something it cannot undo."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFontDatabase
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QLabel, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget

from ai_agent.i18n import tr


def confirm_destructive(parent: QWidget, lines: list[str], details: str = "") -> bool:
    if (details or "").strip():
        return _confirm_code(parent, lines, details)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(tr("Destructive steps"))
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(destructive_confirmation_text(lines, details))
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes


def confirm_delete_conversation(parent: QWidget, title: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(tr("Delete the conversation?"))
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(tr("“{0}” will be deleted for good: it cannot be restored.").format(title))
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.button(QMessageBox.StandardButton.Yes).setText(tr("Delete"))
    return box.exec() == QMessageBox.StandardButton.Yes


def confirm_data_sharing(parent: QWidget, endpoint: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(tr("Share project data?"))
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(
        tr(
            "Send the request to {0}?\n\n"
            "The provider receives your prompt and everything the agent reads to answer it: layer and "
            "field names, feature values, extents, layer sources and rendered map images. For data that "
            "must stay on this computer, use a local model server."
        ).format(endpoint)
    )
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    return box.exec() == QMessageBox.StandardButton.Yes


def _confirm_code(parent: QWidget, lines: list[str], details: str) -> bool:
    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("Destructive steps"))
    dialog.setMinimumWidth(720)
    column = QVBoxLayout(dialog)
    summary = QLabel(_destructive_steps_text(lines))
    summary.setTextFormat(Qt.TextFormat.PlainText)
    summary.setWordWrap(True)
    column.addWidget(summary)
    code_title = QLabel(tr("\n\nExact code to be executed:\n\n{0}").format("").strip())
    code_title.setTextFormat(Qt.TextFormat.PlainText)
    column.addWidget(code_title)
    code = QPlainTextEdit((details or "").strip())
    code.setReadOnly(True)
    code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    code.setMinimumHeight(240)
    column.addWidget(code)
    question = QLabel(tr("\n\nApply them?").strip())
    question.setTextFormat(Qt.TextFormat.PlainText)
    column.addWidget(question)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    buttons.button(QDialogButtonBox.StandardButton.No).setDefault(True)
    column.addWidget(buttons)
    return dialog.exec() == QDialog.DialogCode.Accepted


def _destructive_steps_text(lines: list[str]) -> str:
    listed = "\n".join(f"• {line}" for line in lines)
    return tr("These steps change or delete data and cannot be undone:\n\n{0}").format(listed)


def destructive_confirmation_text(lines: list[str], details: str = "") -> str:
    message = _destructive_steps_text(lines)
    exact = (details or "").strip()
    if exact:
        message += tr("\n\nExact code to be executed:\n\n{0}").format(exact)
    return message + tr("\n\nApply them?")
