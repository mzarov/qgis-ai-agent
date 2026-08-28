import shutil
import tempfile
import unittest

from qgis_ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from qgis_ai_agent.core.state.conversation import ConversationState
from qgis_ai_agent.core.state.store import SessionStore, current_project_key


class Dock:
    def __init__(self):
        self.system = []
        self.replayed = None
        self.sessions_source = None

    def add_system_message(self, text):
        self.system.append(text)
        return 0

    def add_user_message(self, text):
        return 0

    def replay(self, messages):
        self.replayed = list(messages)

    def set_session_source(self, provider):
        self.sessions_source = provider

    def clear_prompt(self):
        return None

    def __getattr__(self, name):
        return lambda *args, **kwargs: 0


class Iface:
    def messageBar(self):
        return self

    def pushMessage(self, *args, **kwargs):
        return None


class Agent:
    def __init__(self):
        self.is_running = False
        self.has_pending_writes = False
        self.is_verification = False
        self.verification_round = 0
        self.started = None
        self.verification_started = None
        self.aborts = 0

    def start(self, prompt, history, verification=False, verification_round=0):
        if verification:
            self.verification_round = verification_round
            self.verification_started = (prompt, list(history))
        else:
            self.started = (prompt, list(history))

    def pending_writes(self):
        return list(getattr(self, "pending", []))

    def confirm_pending(self):
        self.confirmed = True

    def abort(self):
        self.aborts += 1
        self.is_running = False
        self.has_pending_writes = False

    def stop(self):
        return None


class Call:
    def __init__(self, name="set_symbol"):
        self.name = name
        self.arguments = {}


class Result:
    def __init__(self, ok=True, payload=None, name="set_symbol"):
        self.ok = ok
        self.payload = payload or {}
        self.call = Call(name)


class OrchestratorSessionTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.dock = Dock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.store = SessionStore(self.root)
        self.orchestrator.conversation = ConversationState(window_limit=4, store=self.store)
        self.orchestrator.agent = Agent()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _ask(self, text):
        self.orchestrator.on_prompt(text)
        self.orchestrator.on_finished(f"ответ на «{text}»")

    def test_prompt_is_stored(self):
        self._ask("сколько слоёв?")
        self.assertEqual(self.orchestrator.conversation.messages[0]["content"], "сколько слоёв?")

    def test_prompt_window_excludes_current_message(self):
        self.orchestrator.on_prompt("первый вопрос")
        self.assertEqual(self.orchestrator.agent.started, ("первый вопрос", []))

    def test_answer_joins_the_same_session(self):
        self._ask("вопрос")
        roles = [item["role"] for item in self.orchestrator.conversation.messages]
        self.assertEqual(roles, ["user", "assistant"])

    def test_new_session_clears_the_view(self):
        self._ask("вопрос")
        self.orchestrator.on_new_session()
        self.assertEqual(self.dock.replayed, [])

    def test_switching_replays_stored_messages(self):
        self._ask("про дороги")
        identifier = self.orchestrator.conversation.recent()[0][0]
        self.orchestrator.on_new_session()
        self.orchestrator.on_session_chosen(identifier)
        self.assertEqual(self.dock.replayed[0]["content"], "про дороги")

    def test_unknown_session_reports_and_keeps_current(self):
        self._ask("текущий")
        self.orchestrator.on_session_chosen("нет-такого")
        self.assertIn("Conversation not found.", self.dock.system)
        self.assertEqual(len(self.orchestrator.conversation.messages), 2)

    def test_switching_while_running_is_refused(self):
        self._ask("вопрос")
        self.orchestrator.agent.is_running = True
        self.orchestrator.on_new_session()
        self.assertIn("Wait for the current task to finish.", self.dock.system)
        self.assertIsNone(self.dock.replayed)

    def test_switching_with_pending_writes_is_refused(self):
        self._ask("вопрос")
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.on_new_session()
        self.assertEqual(len(self.orchestrator.conversation.messages), 2)
        self.assertIsNone(self.dock.replayed)

    def test_switching_drops_the_stale_plan_card(self):
        self._ask("вопрос")
        self.orchestrator._plan_message_id = 7
        self.orchestrator.on_new_session()
        self.assertIsNone(self.orchestrator._plan_message_id)

    def test_session_source_is_handed_to_the_dock(self):
        self.assertIsNotNone(self.dock.sessions_source)

    def test_empty_prompt_starts_nothing(self):
        self.orchestrator.on_prompt("   ")
        self.assertIsNone(self.orchestrator.agent.started)
        self.assertEqual(self.orchestrator.conversation.messages, [])

    def test_applied_writes_reach_the_next_turn(self):
        self.orchestrator.on_prompt("построй буфер")
        self.orchestrator.on_applied([Result(payload={"result_layer_name": "буфер"})])
        self.orchestrator.on_prompt("а теперь покрась его")
        history = self.orchestrator.agent.started[1]
        self.assertIn("Done: 1 step(s) applied", history[-1]["content"])
        self.assertIn("буфер", history[-1]["content"])

    def test_failed_writes_reach_the_next_turn(self):
        self.orchestrator.on_prompt("построй буфер")
        self.orchestrator.on_applied([Result(ok=False, payload={"error": "нет такого слоя"})])
        self.orchestrator.on_prompt("почини")
        self.assertIn("нет такого слоя", str(self.orchestrator.agent.started[1]))

    def test_destructive_steps_ask_an_extra_confirmation(self):
        from qgis_ai_agent.core.orchestrator import orchestrator as module

        saved = module.get_tool_by_name

        class Destructive:
            safety = "destructive"

        module.get_tool_by_name = lambda name: Destructive()
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.agent.pending = [Call("delete_features")]
        self.dock.confirm_destructive = lambda lines: False
        try:
            self.orchestrator.on_confirm_plan()
        finally:
            module.get_tool_by_name = saved
        self.assertFalse(getattr(self.orchestrator.agent, "confirmed", False))
        self.assertTrue(any("destructive" in text or "не применены" in text for text in self.dock.system))

    def test_accepted_destructive_steps_apply(self):
        from qgis_ai_agent.core.orchestrator import orchestrator as module

        saved = module.get_tool_by_name

        class Destructive:
            safety = "destructive"

        module.get_tool_by_name = lambda name: Destructive()
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.agent.pending = [Call("delete_features")]
        self.dock.confirm_destructive = lambda lines: True
        try:
            self.orchestrator.on_confirm_plan()
        finally:
            module.get_tool_by_name = saved
        self.assertTrue(self.orchestrator.agent.confirmed)

    def test_plain_writes_skip_the_extra_confirmation(self):
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.agent.pending = [Call("set_symbol")]
        asked = []
        self.dock.confirm_destructive = lambda lines: asked.append(lines) or True
        self.orchestrator.on_confirm_plan()
        self.assertEqual(asked, [])
        self.assertTrue(self.orchestrator.agent.confirmed)

    def test_apply_triggers_a_verification_run(self):
        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.on_applied([Result(name="set_symbol")])
        prompt, history = self.orchestrator.agent.verification_started
        self.assertIn("set_symbol: ok", prompt)
        self.assertIn("Verify", prompt)
        self.assertTrue(any("Done: 1 step(s) applied" in item["content"] for item in history))

    def test_failed_steps_reach_the_verification_prompt(self):
        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.on_applied([Result(ok=False, payload={"error": "no such layer"}, name="set_symbol")])
        prompt, _ = self.orchestrator.agent.verification_started
        self.assertIn("FAILED — no such layer", prompt)

    def test_verification_iterates_but_stops_at_the_cap(self):
        from qgis_ai_agent.core.orchestrator.orchestrator import MAX_VERIFICATION_ROUNDS

        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.agent.verification_round = MAX_VERIFICATION_ROUNDS
        self.orchestrator.on_applied([Result()])
        self.assertIsNone(self.orchestrator.agent.verification_started)

    def test_a_failed_fix_gets_another_verification_round(self):
        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.agent.verification_round = 1
        self.orchestrator.on_applied([Result(ok=False, payload={"error": "still wrong"})])
        self.assertIsNotNone(self.orchestrator.agent.verification_started)
        self.assertEqual(self.orchestrator.agent.verification_round, 2)

    def test_verification_respects_the_setting(self):
        from qgis_ai_agent.core.orchestrator import orchestrator as module

        saved = module.get_verify_after_apply
        module.get_verify_after_apply = lambda: False
        try:
            self.orchestrator.on_prompt("сделай реки синими")
            self.orchestrator.on_applied([Result()])
        finally:
            module.get_verify_after_apply = saved
        self.assertIsNone(self.orchestrator.agent.verification_started)

    def test_empty_apply_verifies_nothing(self):
        self.orchestrator.on_prompt("вопрос")
        self.orchestrator.on_applied([])
        self.assertIsNone(self.orchestrator.agent.verification_started)

    def test_stop_aborts_the_run(self):
        self.orchestrator.on_prompt("долгая задача")
        self.orchestrator.agent.is_running = True
        self.orchestrator.on_stop()
        self.assertEqual(self.orchestrator.agent.aborts, 1)

    def test_aborted_run_is_reported_and_unblocks_switching(self):
        self.orchestrator.on_prompt("долгая задача")
        self.orchestrator.agent.is_running = True
        self.orchestrator.on_stop()
        self.orchestrator.on_aborted()
        self.assertTrue(any("Run stopped" in text for text in self.dock.system))
        self.orchestrator.on_new_session()
        self.assertEqual(self.dock.replayed, [])

    def test_aborted_run_drops_the_plan_card(self):
        self.orchestrator._plan_message_id = 3
        self.orchestrator.on_aborted()
        self.assertIsNone(self.orchestrator._plan_message_id)

    def test_question_asked_before_stop_stays_in_the_session(self):
        self.orchestrator.on_prompt("долгая задача")
        self.orchestrator.agent.is_running = True
        self.orchestrator.on_stop()
        self.orchestrator.on_aborted()
        self.assertEqual(self.orchestrator.conversation.messages[-1]["content"], "долгая задача")

    def test_shutdown_saves_the_session(self):
        self._ask("последний вопрос")
        self.orchestrator.shutdown()
        stored = self.store.recent(current_project_key())
        self.assertEqual(stored[0].messages[0]["content"], "последний вопрос")


if __name__ == "__main__":
    unittest.main()
