from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ai_agent.i18n import tr
from ai_agent.ui import style

TITLE = tr("What the agent can do")
WINDOW_WIDTH = 480
WINDOW_HEIGHT = 560
SAFETY_LABELS = {
    "read": tr("runs immediately"),
    "write": tr("waits for Apply"),
    "destructive": tr("asks separately"),
}
NETWORK_LABEL = tr("waits for Apply")
NAME_FONT_SCALE = 0.95


class ToolBrowserDialog(QDialog):
    def __init__(self, capabilities: list[dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(6)
        palette = self.palette()
        for skill in capabilities:
            column.addWidget(_skill_header(skill, palette))
            for tool in skill.get("tools", []):
                column.addWidget(_tool_row(tool, palette))
        column.addStretch(1)
        area.setWidget(holder)
        outer.addWidget(area)


def _skill_header(skill: dict[str, Any], palette) -> QWidget:
    label = QLabel(f"{skill.get('name', '')} — {skill.get('description', '')}")
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.text(palette))}; padding-top: 8px;")
    return label


def _tool_row(tool: dict[str, Any], palette) -> QWidget:
    safety = SAFETY_LABELS.get(str(tool.get("safety", "")), str(tool.get("safety", "")))
    behaviour = NETWORK_LABEL if tool.get("network_access") else safety
    label = QLabel(f"{tool.get('name', '')} · {behaviour}\n{tool.get('description', '')}")
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * NAME_FONT_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; padding-left: 12px;")
    return label
