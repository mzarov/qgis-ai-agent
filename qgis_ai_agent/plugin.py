import os
from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis_ai_agent import i18n
from qgis_ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from qgis_ai_agent.ui.dock_widget import AgentDockWidget
from qgis_ai_agent.ui.settings_dialog import SettingsDialog

MENU_TITLE = "QGIS AI Agent"
DOCK_AREA = getattr(
    getattr(Qt, "DockWidgetArea", Qt), "RightDockWidgetArea", getattr(Qt, "RightDockWidgetArea", 2)
)
ICON_FILENAME = "icon.png"


class QgisAiAgentPlugin:
    def __init__(self, iface: Any):
        self.iface = iface
        self.dock_widget = None
        self.menu_action = None
        self._orchestrator = None
        i18n.install(os.path.dirname(os.path.abspath(__file__)))

    def initGui(self) -> None:
        self.menu_action = QAction(self._icon(), MENU_TITLE, self.iface.mainWindow())
        self.menu_action.triggered.connect(self.run)
        self.iface.addPluginToMenu(MENU_TITLE, self.menu_action)
        self.iface.addToolBarIcon(self.menu_action)

    def unload(self) -> None:
        if self.menu_action:
            self.iface.removePluginMenu(MENU_TITLE, self.menu_action)
            self.iface.removeToolBarIcon(self.menu_action)
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget = None
        if self._orchestrator:
            self._orchestrator.shutdown()
        self._orchestrator = None
        i18n.remove()

    def run(self) -> None:
        if self.dock_widget is None:
            self._build()
        self.iface.addDockWidget(DOCK_AREA, self.dock_widget)
        self.dock_widget.show()
        self.dock_widget.raise_()

    def _build(self) -> None:
        self.dock_widget = AgentDockWidget(self.iface.mainWindow())
        self._orchestrator = CoreOrchestrator(self.iface, self.dock_widget)
        self.dock_widget.prompt_submitted.connect(self._orchestrator.on_prompt)
        self.dock_widget.stop_clicked.connect(self._orchestrator.on_stop)
        self.dock_widget.confirm_plan_clicked.connect(self._orchestrator.on_confirm_plan)
        self.dock_widget.cancel_plan_clicked.connect(self._orchestrator.on_cancel_plan)
        self.dock_widget.new_session_clicked.connect(self._orchestrator.on_new_session)
        self.dock_widget.session_chosen.connect(self._orchestrator.on_session_chosen)
        self.dock_widget.open_settings_clicked.connect(self._on_open_settings)

    def _icon(self) -> QIcon:
        plugin_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
        icon_path = os.path.join(plugin_root, ICON_FILENAME)
        return QIcon(icon_path) if os.path.isfile(icon_path) else QIcon()

    def _on_open_settings(self) -> None:
        SettingsDialog(self.dock_widget).exec()
