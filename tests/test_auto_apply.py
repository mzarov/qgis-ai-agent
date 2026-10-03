import unittest
from types import SimpleNamespace
from unittest import mock

from ai_agent.core.agent import auto_apply
from ai_agent.core.agent import loop as loop_module
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_WRITE


def tool(safety: str):
    return SimpleNamespace(safety_for=lambda _arguments: safety)


def calls(*names: str):
    return [SimpleNamespace(name=name, arguments={}) for name in names]


TOOLS = {
    "set_opacity": tool(SAFETY_WRITE),
    "download_osm": tool(SAFETY_WRITE),
    "delete_features": tool(SAFETY_DESTRUCTIVE),
}


class AppliesItselfTest(unittest.TestCase):
    def check(self, enabled: bool, batch) -> bool:
        with (
            mock.patch.object(auto_apply, "get_auto_apply", return_value=enabled),
            mock.patch.object(auto_apply, "get_tool_by_name", side_effect=TOOLS.get),
        ):
            return auto_apply.applies_itself(batch)

    def test_auto_mode_lets_ordinary_and_network_writes_through(self):
        self.assertTrue(self.check(True, calls("set_opacity", "download_osm")))

    def test_the_button_stays_when_the_mode_is_off(self):
        self.assertFalse(self.check(False, calls("set_opacity")))

    def test_one_destructive_or_unknown_step_holds_the_whole_batch(self):
        self.assertFalse(self.check(True, calls("set_opacity", "delete_features")))
        self.assertFalse(self.check(True, calls("set_opacity", "no_such_tool")))
        self.assertFalse(self.check(True, []))


class LoopOfferTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.offers: list[bool] = []
        self.loop.confirm_needed.connect(lambda _calls, _text, auto: self.offers.append(auto))
        self.loop._batch = mock.MagicMock()
        self.loop._batch.pending.return_value = calls("set_opacity")
        self.loop._batch.__bool__.return_value = True

    def test_a_finished_run_offers_the_batch_with_the_auto_verdict(self):
        with mock.patch.object(loop_module, "applies_itself", return_value=True):
            self.loop._complete("done")
        self.assertEqual(self.offers, [True])

    def test_a_failed_run_never_applies_by_itself(self):
        with mock.patch.object(loop_module, "applies_itself", return_value=True):
            self.loop._fail("boom")
        self.assertEqual(self.offers, [False])


class OrchestratorPressTest(unittest.TestCase):
    def test_an_auto_batch_is_pressed_for_the_user_once_the_card_is_drawn(self):
        from ai_agent.core.orchestrator import orchestrator as orchestrator_module
        from ai_agent.core.orchestrator import plans as plans_module
        from tests.test_orchestrator import Iface, PlanDock

        dock = PlanDock()
        core = orchestrator_module.CoreOrchestrator(Iface(), dock)
        with mock.patch.object(plans_module, "QTimer") as timer:
            core.on_confirm_needed(calls("set_opacity"), "", True)
            core.on_confirm_needed(calls("set_opacity"), "", False)
        self.assertEqual(timer.singleShot.call_count, 1)
        self.assertEqual(timer.singleShot.call_args.args[1], core.on_confirm_plan)
        self.assertFalse(dock.applies_itself)


class ComposerModeTest(unittest.TestCase):
    def test_shift_tab_cycles_and_a_stored_mode_is_shown_silently(self):
        from ai_agent.ui.composer import Composer

        composer = Composer()
        seen: list[str] = []
        composer.mode_changed.connect(seen.append)
        composer.set_mode("auto")
        self.assertEqual((seen, composer.mode, composer.toolbar.mode.text()), ([], "auto", "Auto"))
        composer._edit.mode_cycled.emit()
        self.assertEqual((seen, composer.toolbar.mode.text()), (["ask"], "Ask first"))

    def test_choosing_in_the_menu_reports_only_a_change(self):
        from ai_agent.ui.composer import Composer

        composer = Composer()
        seen: list[str] = []
        composer.mode_changed.connect(seen.append)
        composer.toolbar.modes.choose("ask")
        composer.toolbar.modes.choose("auto")
        self.assertEqual(seen, ["auto"])


class WorkModeSettingTest(unittest.TestCase):
    def test_an_unknown_stored_mode_reads_as_ask(self):
        from ai_agent.core import settings

        with mock.patch.object(settings, "QgsSettings") as stored:
            stored.return_value.value.return_value = "yolo"
            self.assertEqual(settings.get_work_mode(), settings.WORK_MODE_ASK)
            self.assertFalse(settings.get_auto_apply())
            stored.return_value.value.return_value = "auto"
            self.assertTrue(settings.get_auto_apply())


if __name__ == "__main__":
    unittest.main()
