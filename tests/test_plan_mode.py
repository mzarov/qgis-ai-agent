import unittest
from unittest import mock

from ai_agent.core.agent import prompts
from ai_agent.core.agent.request import build_tool_schemas_for
from ai_agent.core.agent.skills import tools_for_skills
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.base import SAFETY_READ


def names(schemas):
    return [schema["function"]["name"] for schema in schemas]


class PlanToolsTest(unittest.TestCase):
    def test_plan_mode_offers_only_the_reading_tools(self):
        planning = tools_for_skills(["style"], writes=False)
        self.assertTrue(planning)
        self.assertTrue(all(tool.safety == SAFETY_READ for tool in planning))
        everything = {tool.name for tool in tools_for_skills(["style"])}
        self.assertIn("set_graduated", everything)
        self.assertNotIn("set_graduated", {tool.name for tool in planning})

    def test_plan_mode_drops_apply_now_but_keeps_the_plan_and_question_tools(self):
        planning = names(build_tool_schemas_for(["inspect"], planning=True))
        self.assertNotIn(prompts.APPLY_NOW_TOOL, planning)
        self.assertIn(prompts.UPDATE_PLAN_TOOL, planning)
        self.assertIn(prompts.ASK_USER_TOOL, planning)
        self.assertIn(prompts.APPLY_NOW_TOOL, names(build_tool_schemas_for(["inspect"])))

    def test_the_mode_rides_in_the_live_state_not_in_the_cached_prompt(self):
        static, live = prompts.build_system_parts("", ["inspect"], planning=True)
        self.assertIn(prompts.PLAN_MODE_NOTE, live)
        self.assertNotIn(prompts.PLAN_MODE_NOTE, static)
        self.assertEqual(static, prompts.build_system_parts("", ["inspect"])[0])


class PlanDispatchTest(unittest.TestCase):
    def test_a_write_called_anyway_is_refused_not_queued(self):
        from ai_agent.core.agent.loop import AgentLoop

        loop = AgentLoop()
        loop._planning = True
        loop._overrides = {}
        result = loop._dispatch_call(
            ToolCall(id="1", name="set_opacity", arguments={"layer_name": "x", "opacity": 0.5})
        )
        self.assertFalse(result.ok)
        self.assertIn("Plan mode", result.payload["error"])
        self.assertFalse(loop._batch)


class PlanOrchestrationTest(unittest.TestCase):
    def setUp(self):
        from ai_agent.core.orchestrator import orchestrator as orchestrator_module
        from tests.test_orchestrator import Agent, Dock, Iface

        self.module = orchestrator_module
        self.dock = Dock()
        self.offers: list[bool] = []
        self.modes: list[str] = []
        self.dock.offer_plan = lambda: self.offers.append(True)
        self.dock.set_work_mode = self.modes.append
        self.core = orchestrator_module.CoreOrchestrator(Iface(), self.dock)
        self.core.agent = Agent()

    def test_a_request_in_plan_mode_starts_a_planning_run(self):
        with mock.patch.object(self.module, "get_planning", return_value=True):
            self.core.on_prompt("раскрась районы")
        self.assertTrue(self.core.agent.planning)

    def test_a_planning_run_ends_on_an_offer_to_run_it(self):
        self.core.agent.is_planning = True
        self.core.on_finished("1. Градуировать районы по населению.")
        self.assertEqual(self.offers, [True])
        self.core.agent.is_planning = False
        self.core.on_finished("Готово.")
        self.assertEqual(self.offers, [True])

    def test_running_the_plan_switches_the_mode_and_asks_for_it(self):
        from ai_agent.core.orchestrator import plans

        self.modes.clear()
        with mock.patch.object(plans, "set_work_mode") as stored:
            self.core.on_run_plan("auto")
        stored.assert_called_once_with("auto")
        self.assertEqual(self.modes, ["auto"])
        self.assertEqual(self.core.agent.started[0], plans.RUN_THE_PLAN_MODEL)

    def test_the_plan_runs_with_the_request_it_was_made_for(self):
        from ai_agent.core.orchestrator import plans

        with mock.patch.object(self.module, "get_planning", return_value=True):
            self.core.on_prompt("раскрась районы")
        with mock.patch.object(plans, "set_work_mode"):
            self.core.on_run_plan("ask")
        self.assertEqual(self.core.agent.started[0], plans.RUN_THE_PLAN_FOR.format("раскрась районы"))
        self.assertEqual(self.core._last_request, "раскрась районы", "the check after Apply needs the real request")

    def test_an_offer_pressed_while_the_agent_works_changes_nothing(self):
        from ai_agent.core.orchestrator import plans

        self.core.agent.is_running = True
        self.modes.clear()
        with mock.patch.object(plans, "set_work_mode") as stored:
            self.core.on_run_plan("auto")
        stored.assert_not_called()
        self.assertEqual(self.modes, [])
        self.assertIsNone(self.core.agent.started)

    def test_no_offer_when_a_limit_ended_the_run(self):
        self.core.agent.is_planning = True
        self.core.agent.ended_on_limit = True
        self.core.on_finished("Reached the limit of turns.")
        self.assertEqual(self.offers, [])


class PlanLoadSkillTest(unittest.TestCase):
    def test_a_skill_loaded_while_planning_lists_no_writing_tool(self):
        from ai_agent.core.agent.skills import load_skill

        call = ToolCall(id="1", name="load_skill", arguments={"names": ["style"]})
        result, _loaded = load_skill(call, [], writes=False)
        self.assertNotIn("set_graduated", result.payload["tools"])
        self.assertIn("describe_style", result.payload["tools"])


class PlanOfferWidgetTest(unittest.TestCase):
    def test_a_new_message_retires_earlier_offers(self):
        from ai_agent.ui.conversation import ConversationView

        view = ConversationView()
        view.add_plan_offer()
        first = view._plan_offers[0]
        view.add_user_message("поменяй план")
        self.assertTrue(all(button.isHidden() for button in first._rows))

    def test_a_choice_reports_its_mode_and_the_buttons_go(self):
        from qgis.PyQt.QtWidgets import QWidget

        from ai_agent.ui.plan import PlanOffer

        offer = PlanOffer(QWidget().palette())
        chosen: list[str] = []
        offer.run_requested.connect(chosen.append)
        offer._run("ask")
        self.assertEqual(chosen, ["ask"])
        self.assertTrue(all(button.isHidden() for button in offer._rows))


if __name__ == "__main__":
    unittest.main()
