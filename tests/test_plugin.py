import unittest
from unittest import mock

from ai_agent import plugin as plugin_module
from ai_agent.plugin import QgisAiAgentPlugin


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, slot):
        self.slots.remove(slot)

    def emit(self):
        for slot in list(self.slots):
            slot()


class Project:
    def __init__(self):
        self.fileNameChanged = Signal()
        self.cleared = Signal()


class Orchestrator:
    def __init__(self, accept_clear=True):
        self.clears = 0
        self.changes = []
        self.accept_clear = accept_clear

    def on_project_cleared(self):
        self.clears += 1
        return self.accept_clear

    def on_project_changed(self, force_new=False):
        self.changes.append(force_new)


class ProjectLifecycleTest(unittest.TestCase):
    def _coalesced(self, order, accept_clear=True):
        project = Project()
        plugin = QgisAiAgentPlugin(object())
        orchestrator = Orchestrator(accept_clear)
        plugin._orchestrator = orchestrator
        queued = []
        with (
            mock.patch.object(plugin_module.QgsProject, "instance", return_value=project),
            mock.patch.object(plugin_module.QTimer, "singleShot", side_effect=lambda delay, call: queued.append(call)),
        ):
            plugin._connect_project_lifecycle()
            for name in order:
                getattr(project, name).emit()
            self.assertEqual(len(queued), 1)
            queued[0]()
        return orchestrator

    def test_clear_forces_reset_when_filename_signal_arrives_first(self):
        orchestrator = self._coalesced(("fileNameChanged", "cleared"))
        self.assertEqual(orchestrator.clears, 1)
        self.assertEqual(orchestrator.changes, [True])

    def test_clear_forces_reset_when_filename_signal_arrives_last(self):
        orchestrator = self._coalesced(("cleared", "fileNameChanged"))
        self.assertEqual(orchestrator.clears, 1)
        self.assertEqual(orchestrator.changes, [True])

    def test_filename_only_keeps_identity_based_deduplication(self):
        orchestrator = self._coalesced(("fileNameChanged",))
        self.assertEqual(orchestrator.clears, 0)
        self.assertEqual(orchestrator.changes, [False])

    def test_agent_owned_project_restore_does_not_force_a_second_reset(self):
        orchestrator = self._coalesced(("cleared", "fileNameChanged"), accept_clear=False)
        self.assertEqual(orchestrator.clears, 1)
        self.assertEqual(orchestrator.changes, [False])


if __name__ == "__main__":
    unittest.main()


class ThemeSwitchTest(unittest.TestCase):
    """A saved panel theme rebuilds the panel at once when the agent is idle, later otherwise."""

    class Iface:
        def __init__(self):
            self.messages = []
            self.removed = []
            self.added = []
            self.window = mock.Mock(dockWidgetArea=lambda dock: 2)

        def mainWindow(self):
            return self.window

        def messageBar(self):
            return mock.Mock(pushMessage=lambda *args, **kwargs: self.messages.append(args))

        def removeDockWidget(self, dock):
            self.removed.append(dock)

        def addDockWidget(self, area, dock):
            self.added.append((area, dock))

    def setUp(self):
        from ai_agent.ui import theme

        self.theme = theme
        self.addCleanup(theme.set_override, theme.THEME_AUTO)

    def _plugin(self, idle):
        iface = self.Iface()
        plugin = QgisAiAgentPlugin(iface)
        plugin.dock_widget = mock.Mock(isVisible=lambda: True)
        plugin._orchestrator = mock.Mock(is_idle=idle)
        return plugin, iface

    def test_an_idle_agent_gets_a_rebuilt_panel_in_the_new_theme(self):
        plugin, iface = self._plugin(idle=True)
        old = plugin.dock_widget
        with (
            mock.patch.object(plugin_module.personal, "load", return_value=mock.Mock(panel_theme="light")),
            mock.patch.object(plugin_module, "AgentDockWidget", return_value=mock.Mock()) as dock_class,
        ):
            plugin._follow_theme()
        self.assertEqual(self.theme.override(), "light")
        self.assertEqual(iface.removed, [old])
        self.assertIs(plugin.dock_widget, dock_class.return_value)
        plugin._orchestrator.attach_dock.assert_called_once_with(plugin.dock_widget)
        self.assertEqual(iface.added, [(2, plugin.dock_widget)])

    def test_a_busy_agent_keeps_the_panel_and_says_when(self):
        plugin, iface = self._plugin(idle=False)
        old = plugin.dock_widget
        with mock.patch.object(plugin_module.personal, "load", return_value=mock.Mock(panel_theme="dark")):
            plugin._follow_theme()
        self.assertEqual(self.theme.override(), "auto")
        self.assertIs(plugin.dock_widget, old)
        self.assertEqual(len(iface.messages), 1)

    def test_an_unchanged_theme_does_nothing(self):
        plugin, iface = self._plugin(idle=True)
        old = plugin.dock_widget
        with mock.patch.object(plugin_module.personal, "load", return_value=mock.Mock(panel_theme="auto")):
            plugin._follow_theme()
        self.assertIs(plugin.dock_widget, old)
        self.assertEqual(iface.removed, [])
