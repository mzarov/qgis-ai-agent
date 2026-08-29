import unittest
from unittest import mock

from qgis_ai_agent import plugin as plugin_module
from qgis_ai_agent.plugin import QgisAiAgentPlugin


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
