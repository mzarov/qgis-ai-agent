import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis_ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from qgis_ai_agent.ui.dock_widget import LayoutAgentDockWidget
from qgis_ai_agent.ui.settings_dialog import SettingsDialog


class QgisAiAgentPlugin:
    """Плагин QGIS AI Agent: bootstrap-слой с инициализацией UI и оркестратора."""

    def __init__(self, iface):
        self.iface = iface
        self.dock_widget = None
        self.menu_action = None
        self._orchestrator = None

    def initGui(self):
        plugin_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
        icon_path = os.path.join(plugin_root, "icon.png")
        icon = QIcon(icon_path) if os.path.isfile(icon_path) else QIcon()
        self.menu_action = QAction(icon, "QGIS AI Agent", self.iface.mainWindow())
        self.menu_action.triggered.connect(self.run)
        self.iface.addPluginToMenu("QGIS AI Agent", self.menu_action)
        self.iface.addToolBarIcon(self.menu_action)

    def unload(self):
        if self.menu_action:
            self.iface.removePluginMenu("QGIS AI Agent", self.menu_action)
            self.iface.removeToolBarIcon(self.menu_action)
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget = None
        if (
            self._orchestrator
            and self._orchestrator.current_llm_thread
            and self._orchestrator.current_llm_thread.isRunning()
        ):
            self._orchestrator.current_llm_thread.terminate()
            self._orchestrator.current_llm_thread.wait(2000)
        self._orchestrator = None

    def run(self):
        if self.dock_widget is None:
            self.dock_widget = LayoutAgentDockWidget(self.iface.mainWindow())
            self._orchestrator = CoreOrchestrator(self.iface, self.dock_widget)
            self.dock_widget.create_layout_from_prompt_clicked.connect(self._orchestrator.on_prompt)
            self.dock_widget.confirm_plan_clicked.connect(self._orchestrator.on_confirm_plan)
            self.dock_widget.cancel_plan_clicked.connect(self._orchestrator.on_cancel_plan)
            self.dock_widget.open_settings_clicked.connect(self._on_open_settings)

        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_widget)
        self.dock_widget.show()
        self.dock_widget.raise_()

    def _on_open_settings(self):
        dlg = SettingsDialog(self.dock_widget)
        dlg.exec()
