import os
from typing import Any

from qgis.core import QgsProject
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QDialog

from ai_agent import i18n
from ai_agent.config import personal
from ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from ai_agent.i18n import tr
from ai_agent.ui import theme
from ai_agent.ui.dock_widget import AgentDockWidget
from ai_agent.ui.settings_dialog import SettingsDialog

MENU_TITLE = "AI Agent"
DOCK_AREA = getattr(getattr(Qt, "DockWidgetArea", Qt), "RightDockWidgetArea", getattr(Qt, "RightDockWidgetArea", 2))
ICON_FILENAME = "icon.png"
THEME_LATER = tr("The panel theme changes once the agent has finished — open Settings and save again then.")
MESSAGE_SECONDS = 8


class QgisAiAgentPlugin:
    def __init__(self, iface: Any):
        self.iface = iface
        self.dock_widget = None
        self.menu_action = None
        self._orchestrator = None
        self._project_sync_pending = False
        self._project_reset_pending = False

    def initGui(self) -> None:
        theme.set_override(personal.load().panel_theme)
        self.menu_action = QAction(self._icon(), MENU_TITLE, self.iface.mainWindow())
        self.menu_action.triggered.connect(self.run)
        self.iface.addPluginToMenu(MENU_TITLE, self.menu_action)
        self.iface.addToolBarIcon(self.menu_action)
        self._connect_project_lifecycle()

    def unload(self) -> None:
        self._disconnect_project_lifecycle()
        if self._orchestrator:
            self._orchestrator.shutdown()
        self._orchestrator = None
        if self.menu_action:
            self.iface.removePluginMenu(MENU_TITLE, self.menu_action)
            self.iface.removeToolBarIcon(self.menu_action)
            self.menu_action.deleteLater()
            self.menu_action = None
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None
        i18n.remove()

    def run(self) -> None:
        if self.dock_widget is None:
            self._build()
        self.iface.addDockWidget(DOCK_AREA, self.dock_widget)
        self.dock_widget.show()
        self.dock_widget.raise_()
        self.dock_widget.focus_prompt()

    def _build(self) -> None:
        self.dock_widget = AgentDockWidget(self.iface.mainWindow())
        self._orchestrator = CoreOrchestrator(self.iface, self.dock_widget)
        self._connect_dock()

    def _connect_dock(self) -> None:
        self.dock_widget.prompt_submitted.connect(self._orchestrator.on_prompt)
        self.dock_widget.stop_clicked.connect(self._orchestrator.on_stop)
        self.dock_widget.files_attached.connect(self._orchestrator.on_files_attached)
        self.dock_widget.work_mode_changed.connect(self._orchestrator.on_work_mode)
        self.dock_widget.compact_requested.connect(self._orchestrator.on_compact)
        self.dock_widget.plan_run_requested.connect(self._orchestrator.on_run_plan)
        self.dock_widget.rewind_requested.connect(self._orchestrator.on_rewind)
        self.dock_widget.plan_undo_requested.connect(self._orchestrator.on_undo_plan)
        self.dock_widget.confirm_plan_clicked.connect(self._orchestrator.on_confirm_plan)
        self.dock_widget.cancel_plan_clicked.connect(self._orchestrator.on_cancel_plan)
        self.dock_widget.new_session_clicked.connect(self._orchestrator.on_new_session)
        self.dock_widget.session_chosen.connect(self._orchestrator.on_session_chosen)
        self.dock_widget.session_renamed.connect(self._orchestrator.on_session_renamed)
        self.dock_widget.session_deleted.connect(self._orchestrator.on_session_deleted)
        self.dock_widget.open_settings_clicked.connect(self._on_open_settings)

    def _icon(self) -> QIcon:
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ICON_FILENAME)
        return QIcon(icon_path) if os.path.isfile(icon_path) else QIcon()

    def _on_open_settings(self) -> None:
        # The main window, not the panel: a reload or a theme rebuild deletes the panel, and its
        # children with it, while the dialog's own event loop is still running.
        dialog = SettingsDialog(self.iface.mainWindow())
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        prompt = dialog.chosen_prompt
        dialog.deleteLater()
        if self._orchestrator is None:
            # Unloaded while the dialog was open: this instance has nothing left to update.
            return
        if accepted and prompt and self.dock_widget:
            self.dock_widget.put_prompt(prompt)
        if self._orchestrator:
            self._orchestrator.refresh_configured()
        if accepted:
            self._follow_theme()

    def _follow_theme(self) -> None:
        """Rebuild the panel in the theme just saved; its colours are fixed when its widgets are made."""
        chosen = personal.load().panel_theme
        if chosen == theme.override():
            return
        if self._orchestrator is not None and not self._orchestrator.is_idle:
            self.iface.messageBar().pushMessage(MENU_TITLE, THEME_LATER, duration=MESSAGE_SECONDS)
            return
        theme.set_override(chosen)
        if self.dock_widget is None or self._orchestrator is None:
            return
        old = self.dock_widget
        area = self.iface.mainWindow().dockWidgetArea(old)
        visible = old.isVisible()
        self.dock_widget = AgentDockWidget(self.iface.mainWindow())
        self._connect_dock()
        self._orchestrator.attach_dock(self.dock_widget)
        self.iface.removeDockWidget(old)
        old.deleteLater()
        self.iface.addDockWidget(area, self.dock_widget)
        self.dock_widget.setVisible(visible)

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
