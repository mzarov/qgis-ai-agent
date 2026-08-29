import os
from typing import Any

from qgis.core import QgsProject
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis_ai_agent import i18n
from qgis_ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from qgis_ai_agent.ui.dock_widget import AgentDockWidget
from qgis_ai_agent.ui.settings_dialog import SettingsDialog

MENU_TITLE = "QGIS AI Agent"
DOCK_AREA = getattr(getattr(Qt, "DockWidgetArea", Qt), "RightDockWidgetArea", getattr(Qt, "RightDockWidgetArea", 2))
ICON_FILENAME = "icon.svg"


class QgisAiAgentPlugin:
    def __init__(self, iface: Any):
        self.iface = iface
        self.dock_widget = None
        self.menu_action = None
        self._orchestrator = None
        self._project_sync_pending = False
        self._project_reset_pending = False

    def initGui(self) -> None:
        self.menu_action = QAction(self._icon(), MENU_TITLE, self.iface.mainWindow())
        self.menu_action.triggered.connect(self.run)
        self.iface.addPluginToMenu(MENU_TITLE, self.menu_action)
        self.iface.addToolBarIcon(self.menu_action)
        self._connect_project_lifecycle()

    def unload(self) -> None:
        self._disconnect_project_lifecycle()
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
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ICON_FILENAME)
        return QIcon(icon_path) if os.path.isfile(icon_path) else QIcon()

    def _on_open_settings(self) -> None:
        SettingsDialog(self.dock_widget).exec()
        if self._orchestrator:
            self._orchestrator.refresh_configured()

    def _connect_project_lifecycle(self) -> None:
        project = QgsProject.instance()
        for signal_name, handler in (
            ("fileNameChanged", self._schedule_project_sync),
            ("cleared", self._schedule_project_reset),
        ):
            try:
                getattr(project, signal_name).connect(handler)
            except (AttributeError, TypeError):
                continue

    def _disconnect_project_lifecycle(self) -> None:
        project = QgsProject.instance()
        for signal_name, handler in (
            ("fileNameChanged", self._schedule_project_sync),
            ("cleared", self._schedule_project_reset),
        ):
            try:
                getattr(project, signal_name).disconnect(handler)
            except (AttributeError, TypeError):
                continue

    def _schedule_project_sync(self, *args: Any) -> None:
        if self._project_sync_pending:
            return
        self._project_sync_pending = True
        QTimer.singleShot(0, self._sync_project)

    def _schedule_project_reset(self, *args: Any) -> None:
        force_new = self._orchestrator is None or self._orchestrator.on_project_cleared()
        self._project_reset_pending = self._project_reset_pending or force_new
        self._schedule_project_sync()

    def _sync_project(self) -> None:
        force_new = self._project_reset_pending
        self._project_sync_pending = False
        self._project_reset_pending = False
        if self._orchestrator is not None:
            self._orchestrator.on_project_changed(force_new=force_new)
