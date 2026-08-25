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
        self.started = None

        self.aborts = 0

    def start(self, prompt, history):
        self.started = (prompt, list(history))

    def abort(self):
        self.aborts += 1
        self.is_running = False
        self.has_pending_writes = False

    def stop(self):
        return None


class Result:
    def __init__(self, ok=True, payload=None):
        self.ok = ok
        self.payload = payload or {}


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
        self.assertIn("Диалог не найден.", self.dock.system)
        self.assertEqual(len(self.orchestrator.conversation.messages), 2)

    def test_switching_while_running_is_refused(self):
        self._ask("вопрос")
        self.orchestrator.agent.is_running = True
        self.orchestrator.on_new_session()
        self.assertIn("Дождитесь окончания текущей задачи.", self.dock.system)
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
        self.assertIn("Готово: применено шагов — 1", history[-1]["content"])
        self.assertIn("буфер", history[-1]["content"])

    def test_failed_writes_reach_the_next_turn(self):
        self.orchestrator.on_prompt("построй буфер")
        self.orchestrator.on_applied([Result(ok=False, payload={"error": "нет такого слоя"})])
        self.orchestrator.on_prompt("почини")
        self.assertIn("нет такого слоя", self.orchestrator.agent.started[1][-1]["content"])

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
        self.assertTrue(any("остановлен" in text for text in self.dock.system))
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
