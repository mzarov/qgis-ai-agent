import shutil
import tempfile
import unittest

from ai_agent.core.orchestrator import notices
from ai_agent.core.orchestrator import orchestrator as orchestrator_module
from ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from ai_agent.core.state import conversation as conversation_module
from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.state.store import SessionStore, current_project_key


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
        self.is_awaiting_answer = False
        self.answered = None
        self.is_verification = False
        self.verification_round = 0
        self.started = None
        self.verification_started = None
        self.aborts = 0
        self.stops = 0
        self.is_applying = False
        self.active_apply_tool = ""

    def start(
        self,
        prompt,
        history,
        verification=False,
        verification_round=0,
        skills=None,
        preload=None,
        images=None,
        planning=False,
    ):
        self.skills = skills
        self.images = images
        self.planning = planning
        self.preload = preload
        if verification:
            self.verification_round = verification_round
            self.verification_started = (prompt, list(history))
        else:
            self.started = (prompt, list(history))

    def pending_writes(self):
        return list(getattr(self, "pending", []))

    def confirm_pending(self):
        self.confirmed = True

    def cancel_pending(self):
        self.cancelled = True
        self.has_pending_writes = False

    def answer(self, text):
        self.answered = text
        self.is_awaiting_answer = False
        return True

    def abort(self):
        self.aborts += 1
        self.is_running = False
        self.is_applying = False
        self.has_pending_writes = False
        self.is_awaiting_answer = False
        self.answered = None

    def stop(self):
        self.stops += 1
        self.abort()


class PlanDock(Dock):
    def __init__(self):
        super().__init__()
        self.cancelled_plans = []
        self.completed_plans = []
        self.failed_plans = []
        self.undone_plans = []
        self.undoable = False
        self.plan_lines = None

    def mark_plan_completed(self, message_id, undoable=False):
        self.completed_plans.append(message_id)
        self.undoable = undoable

    def mark_plan_failed(self, message_id, undoable=False):
        self.failed_plans.append(message_id)
        self.undoable = undoable

    def mark_plan_undone(self, message_id):
        self.undone_plans.append(message_id)

    def add_plan_message(self, lines, applies_itself=False):
        self.plan_lines = list(lines)
        self.applies_itself = applies_itself
        return 7

    def mark_plan_cancelled(self, message_id):
        self.cancelled_plans.append(message_id)


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
        self.orchestrator.conversation = ConversationState(store=self.store)
        self.orchestrator.agent = Agent()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _ask(self, text):
        self.orchestrator.on_prompt(text)
        self.orchestrator.on_finished(f"ответ на «{text}»")

    def test_prompt_is_stored(self):
        self._ask("сколько слоёв?")
        self.assertEqual(self.orchestrator.conversation.messages[0]["content"], "сколько слоёв?")

    def test_slash_prefix_preloads_the_skill_and_strips_the_command(self):
        self._ask("/osm скачай кафе")
        self.assertEqual(self.orchestrator.agent.started[0], "скачай кафе")
        self.assertEqual(self.orchestrator.agent.skills, ["osm"])
        self.assertEqual(self.orchestrator.conversation.messages[0]["content"], "/osm скачай кафе")

    def test_bare_slash_skill_gets_a_default_prompt(self):
        self._ask("/osm")
        self.assertIn("'osm'", self.orchestrator.agent.started[0])

    def test_unknown_slash_command_is_refused_with_the_list(self):
        self._ask("/nope do something")
        self.assertIsNone(self.orchestrator.agent.started)
        self.assertTrue(any("/osm" in line for line in self.dock.system))

    def test_plain_text_never_passes_skills(self):
        self._ask("скачай кафе")
        self.assertIsNone(self.orchestrator.agent.skills)

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

    def test_switching_while_running_stops_the_run_instead_of_refusing(self):
        self._ask("вопрос")
        self.orchestrator.agent.is_running = True
        self.orchestrator.on_new_session()
        self.assertEqual(self.orchestrator.agent.aborts, 1)
        self.assertNotIn("Wait for the current task to finish.", self.dock.system)

    def test_switching_with_pending_writes_drops_them_instead_of_refusing(self):
        self._ask("вопрос")
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.on_new_session()
        self.assertEqual(self.orchestrator.agent.aborts, 1)

    def test_switching_while_waiting_for_an_answer_stops_the_question(self):
        self._ask("вопрос")
        self.orchestrator.agent.is_awaiting_answer = True
        self.orchestrator.on_new_session()
        self.assertEqual(self.orchestrator.agent.aborts, 1)

    def test_switching_while_applying_is_still_refused(self):
        self._ask("вопрос")
        self.orchestrator.agent.is_applying = True
        self.orchestrator.on_new_session()
        self.assertIn(notices.SWITCH_WHILE_APPLYING, self.dock.system)
        self.assertIsNone(self.dock.replayed)

    def test_project_change_aborts_old_run_and_starts_project_scoped_session(self):
        self._ask("про старый проект")
        self.orchestrator.agent.is_awaiting_answer = True
        saved = conversation_module.current_project_key
        conversation_module.current_project_key = lambda: "/new/project.qgz"
        try:
            self.orchestrator.on_project_changed()
        finally:
            conversation_module.current_project_key = saved
        self.assertEqual(self.orchestrator.agent.aborts, 1)
        self.assertEqual(self.orchestrator.conversation.project_key, "/new/project.qgz")
        self.assertEqual(self.dock.replayed, [])
        self.assertIn(notices.PROJECT_CHANGED, self.dock.system)

    def test_interrupted_apply_from_old_project_never_pollutes_the_new_session(self):
        self._ask("work in the old project")
        old_identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.on_confirm_plan()
        self.orchestrator.agent.is_applying = True
        drawn = []
        self.dock.add_result_message = drawn.append
        saved = conversation_module.current_project_key
        conversation_module.current_project_key = lambda: "/new/project.qgz"
        try:
            self.orchestrator.on_project_changed()
        finally:
            conversation_module.current_project_key = saved

        self.orchestrator.on_apply_interrupted([Result(ok=True, name="set_symbol")])

        self.assertEqual(self.orchestrator.conversation.project_key, "/new/project.qgz")
        self.assertEqual(self.orchestrator.conversation.messages, [])
        self.assertEqual(drawn, [])
        old_session = self.store.load(old_identifier)
        self.assertTrue(any("Stopped after 1 completed step" in item["content"] for item in old_session.messages))
        self.assertIn(notices.PREVIOUS_APPLY_INTERRUPTED, self.dock.system)
        self.assertIsNone(self.orchestrator._apply_scope)

    def test_transient_filename_signal_does_not_restart_the_conversation(self):
        self._ask("тот же проект")
        identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.on_project_changed()
        self.assertEqual(self.orchestrator.conversation.session_identifier, identifier)

    def test_clear_reload_same_key_aborts_apply_and_starts_a_fresh_session(self):
        self._ask("delete selected parcels")
        identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.agent.is_applying = True
        saved = conversation_module.current_project_key
        conversation_module.current_project_key = lambda: self.orchestrator.conversation.project_key
        try:
            self.orchestrator.on_project_cleared()
            self.assertEqual(self.orchestrator.agent.aborts, 1)
            self.orchestrator.on_project_changed(force_new=True)
        finally:
            conversation_module.current_project_key = saved

        self.assertFalse(self.orchestrator.agent.has_pending_writes)
        self.assertFalse(self.orchestrator.agent.is_applying)
        self.assertNotEqual(self.orchestrator.conversation.session_identifier, identifier)
        self.assertEqual(self.orchestrator.conversation.messages, [])
        self.assertEqual(self.dock.replayed, [])

    def test_partial_result_before_deferred_reload_is_reported_after_replay(self):
        self._ask("change the old project")
        old_identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.on_confirm_plan()
        self.orchestrator.agent.is_applying = True
        drawn = []
        self.dock.add_result_message = drawn.append

        self.assertTrue(self.orchestrator.on_project_cleared())
        self.orchestrator.on_apply_interrupted([Result(ok=True, name="set_symbol")])
        self.assertEqual(drawn, [])
        self.assertNotIn(notices.PREVIOUS_APPLY_INTERRUPTED, self.dock.system)

        saved = conversation_module.current_project_key
        conversation_module.current_project_key = lambda: self.orchestrator.conversation.project_key
        try:
            self.orchestrator.on_project_changed(force_new=True)
        finally:
            conversation_module.current_project_key = saved

        self.assertEqual(self.orchestrator.conversation.messages, [])
        self.assertIn(notices.PREVIOUS_APPLY_INTERRUPTED, self.dock.system)
        self.assertTrue(any("Stopped after 1 completed step" in message for message in self.dock.system))
        old_session = self.store.load(old_identifier)
        self.assertTrue(any("Stopped after 1 completed step" in item["content"] for item in old_session.messages))

    def test_clear_from_the_executing_undo_does_not_cancel_that_undo(self):
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.agent.is_applying = True
        self.orchestrator.agent.active_apply_tool = "undo_last_apply"

        self.assertFalse(self.orchestrator.on_project_cleared())
        self.assertEqual(self.orchestrator.agent.aborts, 0)
        self.assertTrue(self.orchestrator.agent.has_pending_writes)

    def test_transient_filename_from_the_executing_undo_is_ignored(self):
        identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.agent.active_apply_tool = "undo_last_apply"
        saved = conversation_module.current_project_key
        conversation_module.current_project_key = lambda: "/temporary/snapshot.qgz"
        try:
            self.orchestrator.on_project_changed()
        finally:
            conversation_module.current_project_key = saved

        self.assertEqual(self.orchestrator.conversation.session_identifier, identifier)
        self.assertEqual(self.orchestrator.agent.aborts, 0)

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

    def _with_remote_endpoint(self, consent: bool, answer: bool) -> list:
        saved = (
            orchestrator_module._is_configured,
            orchestrator_module.get_api_url,
            orchestrator_module.get_data_sharing_consent,
            orchestrator_module.set_data_sharing_consent,
        )
        remembered: list = []
        orchestrator_module._is_configured = lambda: True
        orchestrator_module.get_api_url = lambda: "https://provider.example/v1"
        orchestrator_module.get_data_sharing_consent = lambda url: consent
        orchestrator_module.set_data_sharing_consent = lambda value, url: remembered.append((value, url))
        self.dock.confirm_data_sharing = lambda endpoint: answer
        try:
            self.orchestrator.on_prompt("inspect the project")
        finally:
            (
                orchestrator_module._is_configured,
                orchestrator_module.get_api_url,
                orchestrator_module.get_data_sharing_consent,
                orchestrator_module.set_data_sharing_consent,
            ) = saved
        return remembered

    def test_first_send_to_a_remote_endpoint_asks_and_remembers_yes(self):
        remembered = self._with_remote_endpoint(consent=False, answer=True)
        self.assertIsNotNone(self.orchestrator.agent.started)
        self.assertEqual(remembered, [(True, "https://provider.example/v1")])

    def test_declined_confirmation_sends_nothing_and_stores_nothing(self):
        remembered = self._with_remote_endpoint(consent=False, answer=False)
        self.assertIsNone(self.orchestrator.agent.started)
        self.assertEqual(remembered, [])
        self.assertIn(notices.DATA_SHARING_DECLINED, self.dock.system)

    def test_a_remembered_endpoint_is_not_asked_again(self):
        asked = []
        self.dock.confirm_data_sharing = lambda endpoint: asked.append(endpoint) or True
        remembered = self._with_remote_endpoint(consent=True, answer=True)
        self.assertIsNotNone(self.orchestrator.agent.started)
        self.assertEqual(remembered, [])

    def test_applied_writes_reach_the_next_turn(self):
        self.orchestrator.on_prompt("построй буфер")
        self.orchestrator.on_applied([Result(payload={"result_layer_name": "буфер"})])
        self.orchestrator.on_prompt("а теперь покрась его")
        history = self.orchestrator.agent.started[1]
        self.assertIn("Done: 1 step applied", history[-1]["content"])
        self.assertIn("буфер", history[-1]["content"])

    def test_failed_writes_reach_the_next_turn(self):
        self.orchestrator.on_prompt("построй буфер")
        self.orchestrator.on_applied([Result(ok=False, payload={"error": "нет такого слоя"})])
        self.orchestrator.on_prompt("почини")
        self.assertIn("нет такого слоя", str(self.orchestrator.agent.started[1]))

    def test_destructive_steps_ask_an_extra_confirmation(self):
        from ai_agent.core.orchestrator import planning as module

        saved = module.get_tool_by_name

        class Destructive:
            def safety_for(self, params):
                return "destructive"

            def detail_call(self, params):
                return ""

        module.get_tool_by_name = lambda name: Destructive()
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.agent.pending = [Call("delete_features")]
        self.dock.confirm_destructive = lambda lines, details="": False
        try:
            self.orchestrator.on_confirm_plan()
        finally:
            module.get_tool_by_name = saved
        self.assertFalse(getattr(self.orchestrator.agent, "confirmed", False))
        self.assertTrue(any("destructive" in text or "не применены" in text for text in self.dock.system))

    def test_accepted_destructive_steps_apply(self):
        from ai_agent.core.orchestrator import planning as module

        saved = module.get_tool_by_name

        class Destructive:
            def safety_for(self, params):
                return "destructive"

            def detail_call(self, params):
                return ""

        module.get_tool_by_name = lambda name: Destructive()
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.agent.pending = [Call("delete_features")]
        self.dock.confirm_destructive = lambda lines, details="": True
        try:
            self.orchestrator.on_confirm_plan()
        finally:
            module.get_tool_by_name = saved
        self.assertTrue(self.orchestrator.agent.confirmed)

    def test_plain_writes_skip_the_extra_confirmation(self):
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.agent.pending = [Call("set_symbol")]
        asked = []
        self.dock.confirm_destructive = lambda lines, details="": asked.append(lines) or True
        self.orchestrator.on_confirm_plan()
        self.assertEqual(asked, [])
        self.assertTrue(self.orchestrator.agent.confirmed)

    def test_apply_triggers_a_verification_run(self):
        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.on_applied([Result(name="set_symbol")])
        prompt, history = self.orchestrator.agent.verification_started
        self.assertIn("set_symbol: ok", prompt)
        self.assertIn("Verify", prompt)
        self.assertTrue(any("Done: 1 step applied" in item["content"] for item in history))

    def test_verification_starts_with_the_skills_of_the_applying_run(self):
        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.agent.loaded_skills = ["inspect", "style"]
        self.orchestrator.on_applied([Result(name="set_symbol")])
        self.assertEqual(self.orchestrator.agent.preload, ["inspect", "style"])

    def test_a_failed_run_keeps_the_partial_answer_and_offers_the_request_again(self):
        restored = []
        self.dock.keep_stream = lambda: "Half an answer"
        self.dock.restore_prompt = restored.append
        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.on_failed("HTTP 500")
        contents = [message["content"] for message in self.orchestrator.conversation.messages]
        self.assertIn("Half an answer", contents)
        self.assertEqual(restored, ["сделай реки синими"])

    def test_a_stopped_run_leaves_the_box_empty(self):
        restored = []
        self.dock.restore_prompt = restored.append
        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.on_aborted()
        self.assertEqual(restored, [])

    def test_failed_steps_reach_the_verification_prompt(self):
        self.orchestrator.on_prompt("сделай реки синими")
        self.orchestrator.on_applied([Result(ok=False, payload={"error": "no such layer"}, name="set_symbol")])
        prompt, _ = self.orchestrator.agent.verification_started
        self.assertIn("FAILED — no such layer", prompt)

    def test_verification_iterates_but_stops_at_the_cap(self):
        from ai_agent.core.agent.verification import MAX_VERIFICATION_ROUNDS

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
        from ai_agent.core.orchestrator import plans as module

        saved = module.get_verify_after_apply
        module.get_verify_after_apply = lambda: False
        try:
            self.orchestrator.on_prompt("сделай реки синими")
            self.orchestrator.on_applied([Result()])
        finally:
            module.get_verify_after_apply = saved
        self.assertIsNone(self.orchestrator.agent.verification_started)

    def test_steps_that_read_back_as_done_skip_the_model_check(self):
        from ai_agent.core.orchestrator import plans as module
        from ai_agent.core.orchestrator.notices import CHECKED_BY_READING

        saved = module.confirmed_by_reading
        module.confirmed_by_reading = lambda results: True
        try:
            self.orchestrator.on_prompt("переименуй слой")
            self.orchestrator.on_applied([Result(name="configure_layer")])
        finally:
            module.confirmed_by_reading = saved
        self.assertIsNone(self.orchestrator.agent.verification_started)
        self.assertIn(CHECKED_BY_READING, self.dock.system)

    def test_empty_apply_verifies_nothing(self):
        self.orchestrator.on_prompt("вопрос")
        self.orchestrator.on_applied([])
        self.assertIsNone(self.orchestrator.agent.verification_started)

    def test_stop_aborts_the_run(self):
        self.orchestrator.on_prompt("долгая задача")
        self.orchestrator.agent.is_running = True
        self.orchestrator.on_stop()
        self.assertEqual(self.orchestrator.agent.aborts, 1)

    def test_prompt_during_apply_is_refused_without_cancelling_or_starting(self):
        self.orchestrator.agent.is_applying = True
        self.orchestrator.agent.has_pending_writes = True

        self.orchestrator.on_prompt("start another run")

        self.assertIsNone(self.orchestrator.agent.started)
        self.assertFalse(getattr(self.orchestrator.agent, "cancelled", False))
        self.assertEqual(self.orchestrator.conversation.messages, [])
        self.assertIn(notices.SWITCH_WHILE_RUNNING, self.dock.system)

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

    def test_abort_while_applying_reports_that_completed_changes_remain(self):
        self.orchestrator.agent.is_applying = True
        self.orchestrator._plan_message_id = 3

        self.orchestrator.on_aborted()

        self.assertIn(notices.APPLY_STOPPED, self.dock.system)
        self.assertNotIn("were dropped", self.dock.system[-1])

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
        self.assertEqual(self.orchestrator.agent.stops, 1)


if __name__ == "__main__":
    unittest.main()


class PendingPlanTest(unittest.TestCase):
    def setUp(self):
        self.dock = PlanDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.agent = Agent()

    def _pending(self):
        self.orchestrator.on_confirm_needed([Call()], "")
        self.orchestrator.agent.has_pending_writes = True

    def test_a_new_message_cancels_the_pending_plan(self):
        self._pending()
        self.orchestrator.on_prompt("ты же уже снял?")
        self.assertTrue(self.orchestrator.agent.cancelled)

    def test_the_stale_card_is_marked_instead_of_staying_live(self):
        self._pending()
        self.orchestrator.on_prompt("ты же уже снял?")
        self.assertEqual(self.dock.cancelled_plans, [7])

    def test_the_user_is_told_the_plan_was_dropped(self):
        self._pending()
        self.orchestrator.on_prompt("ты же уже снял?")
        self.assertIn(notices.PLAN_DROPPED, self.dock.system)

    def test_the_new_run_still_starts(self):
        self._pending()
        self.orchestrator.on_prompt("ты же уже снял?")
        self.assertEqual(self.orchestrator.agent.started[0], "ты же уже снял?")

    def test_nothing_is_cancelled_when_no_plan_is_pending(self):
        self.orchestrator.on_prompt("сколько слоёв?")
        self.assertFalse(getattr(self.orchestrator.agent, "cancelled", False))
        self.assertEqual(self.dock.cancelled_plans, [])

    def test_a_running_agent_is_still_interjected_not_cancelled(self):
        self._pending()
        self.orchestrator.agent.is_running = True
        self.orchestrator.agent.interject = lambda text: True
        self.orchestrator.on_prompt("подожди")
        self.assertFalse(getattr(self.orchestrator.agent, "cancelled", False))


class PlanCardLinesTest(unittest.TestCase):
    def setUp(self):
        self.dock = PlanDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.agent = Agent()

    def test_the_step_text_carries_no_number_of_its_own(self):
        self.orchestrator.on_confirm_needed([Call(), Call("set_labels")], "")
        for line in self.dock.plan_lines:
            self.assertFalse(line.lstrip().startswith("1."))
            self.assertFalse(line.lstrip().startswith("2."))

    def test_every_call_still_gets_a_line(self):
        self.orchestrator.on_confirm_needed([Call(), Call("set_labels"), Call("add_basemap")], "")
        self.assertEqual(len(self.dock.plan_lines), 3)

    def test_an_ordinary_step_leaves_undo_to_the_card(self):
        line = self.orchestrator._plan_line(Call("set_symbol"))
        self.assertNotIn(" · ", line)

    def test_plan_warns_that_external_outputs_are_not_undone(self):
        line = self.orchestrator._plan_line(Call("export_layout"))
        self.assertIn("outside the project", line)

    def test_plan_marks_arbitrary_python_as_potentially_irreversible(self):
        line = self.orchestrator._plan_line(Call("run_python"))
        self.assertIn("irreversible", line)


class AskUserFlowTest(unittest.TestCase):
    def setUp(self):
        self.dock = PlanDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.agent = Agent()

    def test_the_question_lands_in_the_chat_with_a_hint(self):
        self.orchestrator.on_question_asked("Какой из двух слоёв дорог брать?")
        self.assertIn(notices.AWAITING_ANSWER, self.dock.system)
        self.assertEqual(self.orchestrator.conversation.messages[-1]["content"], "Какой из двух слоёв дорог брать?")

    def test_offered_answers_become_a_card_and_stay_in_the_session(self):
        shown = []
        self.dock.add_question = lambda question, options: shown.append((question, options)) or 0
        self.orchestrator.agent.question_options = ["roads_2024", "roads_old"]
        self.orchestrator.on_question_asked("Which roads layer?")
        self.assertEqual(shown, [("Which roads layer?", ["roads_2024", "roads_old"])])
        self.assertNotIn(notices.AWAITING_ANSWER, self.dock.system)
        self.assertEqual(
            self.orchestrator.conversation.messages[-1]["content"], "Which roads layer?\n\n- roads_2024\n- roads_old"
        )

    def test_the_next_message_is_routed_as_the_answer(self):
        self.orchestrator.agent.is_awaiting_answer = True
        self.orchestrator.on_prompt("бери layer_roads_2024")
        self.assertEqual(self.orchestrator.agent.answered, "бери layer_roads_2024")
        self.assertIsNone(self.orchestrator.agent.started)

    def test_an_answer_does_not_drop_the_queued_plan(self):
        self.orchestrator.agent.is_awaiting_answer = True
        self.orchestrator.agent.has_pending_writes = True
        self.orchestrator.on_prompt("бери первый")
        self.assertFalse(getattr(self.orchestrator.agent, "cancelled", False))

    def test_without_a_question_the_message_starts_a_run_as_before(self):
        self.orchestrator.on_prompt("сколько слоёв?")
        self.assertEqual(self.orchestrator.agent.started[0], "сколько слоёв?")
        self.assertIsNone(self.orchestrator.agent.answered)


class PreambleFlowTest(unittest.TestCase):
    def setUp(self):
        self.dock = PlanDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.agent = Agent()

    def test_the_preamble_is_saved_like_any_answer(self):
        self.orchestrator.on_preamble("Сейчас скачаю кафе.")
        self.assertEqual(self.orchestrator.conversation.messages[-1]["content"], "Сейчас скачаю кафе.")
        self.assertEqual(self.orchestrator.conversation.messages[-1]["role"], "assistant")


class StageAppliedTest(unittest.TestCase):
    def setUp(self):
        self.dock = PlanDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.agent = Agent()

    def test_a_staged_apply_settles_its_card(self):
        self.orchestrator.on_confirm_needed([Call()], "")
        self.orchestrator.on_stage_applied([Result()])
        self.assertEqual(self.dock.completed_plans, [7])
        self.assertIsNone(self.orchestrator._plan_message_id)

    def test_without_a_card_nothing_is_marked(self):
        self.orchestrator.on_stage_applied([Result()])
        self.assertEqual(self.dock.completed_plans, [])

    def test_a_failed_stage_marks_the_card_failed(self):
        self.orchestrator.on_confirm_needed([Call()], "")
        self.orchestrator.on_stage_applied([Result(ok=False, payload={"error": "snapshot failed"})])
        self.assertEqual(self.dock.failed_plans, [7])

    def test_interrupted_mixed_batch_surfaces_partial_success_without_verification(self):
        self.orchestrator.agent.is_applying = True
        self.orchestrator._apply_scope = (
            self.orchestrator.conversation.project_key,
            self.orchestrator.conversation.session_identifier,
        )
        self.orchestrator.on_confirm_needed([Call("set_symbol"), Call("fetch_url")], "")
        self.orchestrator.on_aborted()
        results = [
            Result(ok=True, payload={"result_layer_name": "styled roads"}, name="set_symbol"),
            Result(ok=False, payload={"error": "request cancelled"}, name="fetch_url"),
        ]

        self.orchestrator.on_apply_interrupted(results)

        self.assertEqual(self.dock.failed_plans, [7])
        messages = [item["content"] for item in self.orchestrator.conversation.messages]
        self.assertTrue(any("Stopped after 1 completed step" in text for text in messages))
        self.assertTrue(any("pending steps were cancelled" in text for text in messages))
        self.assertIsNone(self.orchestrator.agent.verification_started)


class FailedApplySettlesTest(unittest.TestCase):
    def test_a_failed_apply_marks_the_card_instead_of_leaving_it_live(self):
        dock = PlanDock()
        orchestrator = CoreOrchestrator(Iface(), dock)
        orchestrator.agent = Agent()
        orchestrator.on_confirm_needed([Call()], "")
        orchestrator.on_applied([Result(ok=False, payload={"error": "boom"})])
        self.assertEqual(dock.failed_plans, [7])
        self.assertEqual(dock.completed_plans, [])
        self.assertIsNone(orchestrator._plan_message_id)


class StepDock(PlanDock):
    def __init__(self):
        super().__init__()
        self.steps = []
        self.tool_rows = []

    def mark_plan_step(self, message_id, index, state, note=""):
        self.steps.append((index, state, note))

    def add_tool_message(self, text):
        self.tool_rows.append(text)
        return len(self.tool_rows)


class PlanProgressTest(unittest.TestCase):
    """While a plan applies, its card shows each step's progress; the feed gets no duplicate rows."""

    def setUp(self):
        self.dock = StepDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.agent = Agent()
        self.orchestrator.on_confirm_needed([Call("download_osm"), Call("set_symbol")], "")

    def test_applying_steps_light_up_in_the_card_with_the_plain_reason(self):
        self.orchestrator.agent.is_applying = True
        self.orchestrator.on_tool_started("Downloading roads")
        self.orchestrator.on_tool_finished("download_osm", False, "The service did not answer in time.")
        self.assertEqual(self.dock.tool_rows, [])
        self.assertEqual(
            self.dock.steps,
            [(0, notices.STEP_RUNNING, ""), (0, notices.STEP_FAILED, "The service did not answer in time.")],
        )
        self.orchestrator.agent.is_applying = False
        gateway = "Could not fetch data from Overpass: server replied: Gateway Timeout."
        self.orchestrator.on_applied(
            [Result(ok=False, payload={"error": gateway}), Result(ok=False, payload={"status": "skipped"})]
        )
        self.assertIn((1, notices.STEP_SKIPPED, ""), self.dock.steps)
        self.assertNotIn(gateway, " ".join(self.dock.system))

    def test_reads_outside_an_apply_still_become_feed_rows(self):
        self.orchestrator.agent.is_applying = False
        self.orchestrator.on_tool_started("Reading layer roads")
        self.assertEqual(self.dock.tool_rows, ["Reading layer roads"])


class FailureWordsTest(unittest.TestCase):
    def test_network_failures_read_as_plain_sentences(self):
        from ai_agent.core.agent import failures

        cases = {
            "Error transferring https://overpass-api.de - server replied: Gateway Timeout": failures.BUSY,
            "server replied: Too Many Requests": failures.RATE_LIMITED,
            "Host overpass-api.de not found": failures.OFFLINE,
            "server replied: Forbidden": failures.DENIED,
            "server replied: Internal Server Error": failures.SERVER_DOWN,
            "Layer 'roads' not found. Available: rivers": failures.GENERIC,
            "": failures.GENERIC,
        }
        for error, sentence in cases.items():
            self.assertEqual(failures.explain_failure(error), sentence, error)


class AttachDockTest(unittest.TestCase):
    def test_a_rebuilt_dock_gets_the_conversation_and_the_idle_check_sees_work(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        orchestrator = CoreOrchestrator(Iface(), Dock())
        orchestrator.conversation = ConversationState(store=SessionStore(root))
        orchestrator.agent = Agent()
        orchestrator.conversation.add("user", "сколько слоёв?")
        self.assertTrue(orchestrator.is_idle)
        fresh = Dock()
        orchestrator.attach_dock(fresh)
        self.assertIs(orchestrator.dock_widget, fresh)
        self.assertIs(orchestrator.compaction._dock, fresh)
        self.assertEqual([message["content"] for message in fresh.replayed], ["сколько слоёв?"])
        orchestrator.agent.is_running = True
        self.assertFalse(orchestrator.is_idle)

    def test_streams_and_busy_follow_the_rebuilt_dock(self):
        orchestrator = CoreOrchestrator(Iface(), Dock())
        seen = []

        class Recorder(Dock):
            def set_busy(self, busy):
                seen.append(("busy", busy))

            def add_stream_chunk(self, text):
                seen.append(("answer", text))

            def add_thinking_chunk(self, text):
                seen.append(("thinking", text))

        orchestrator.attach_dock(Recorder())
        orchestrator.on_busy(True)
        orchestrator.on_answer_chunk("Hel")
        orchestrator.on_thinking_chunk("hmm")
        self.assertEqual(seen, [("busy", True), ("answer", "Hel"), ("thinking", "hmm")])


class PlanUndoTest(unittest.TestCase):
    """The card's Undo restores the snapshot its apply took, and only when one exists and nothing runs."""

    def setUp(self):
        from unittest import mock

        from ai_agent.core.orchestrator import plans as plans_module
        from ai_agent.core.orchestrator import rewind as rewind_module

        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.dock = PlanDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.conversation = ConversationState(store=SessionStore(self.root))
        self.orchestrator.agent = Agent()
        self.orchestrator.conversation.add("user", "покрась районы")
        self.snapshots = ["/tmp/before.qgz"]
        for module in (plans_module, rewind_module):
            patcher = mock.patch.object(module, "last_snapshot", side_effect=lambda: self.snapshots[-1])
            patcher.start()
            self.addCleanup(patcher.stop)
        self.restored = []
        self.dropped = []
        for name, value in (
            ("snapshot_exists", lambda path: path in self.snapshots),
            ("restore_snapshot", lambda path: self.restored.append(path) or {}),
            ("drop_snapshot", self.dropped.append),
        ):
            patcher = mock.patch.object(rewind_module, name, side_effect=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _apply(self):
        self.orchestrator.on_confirm_needed([Call()], "")
        self.orchestrator._note_apply_start()
        self.snapshots.append("/tmp/after-plan.qgz")
        self.orchestrator.on_applied([Result(ok=True)])

    def test_an_applied_plan_can_be_undone_from_its_card(self):
        self._apply()
        self.assertTrue(self.dock.undoable)
        self.orchestrator.on_undo_plan(7)
        self.assertEqual(self.restored, ["/tmp/after-plan.qgz"])
        self.assertEqual(self.dock.undone_plans, [7])
        self.assertIn("undone", self.orchestrator.conversation.messages[-1]["content"])

    def test_a_vanished_snapshot_says_so(self):
        self._apply()
        self.snapshots.remove("/tmp/after-plan.qgz")
        self.orchestrator.on_undo_plan(7)
        self.assertEqual(self.restored, [])
        self.assertTrue(any("can no longer be undone" in text for text in self.dock.system))

    def test_nothing_is_undone_while_the_agent_works(self):
        self._apply()
        self.orchestrator.agent.is_running = True
        self.orchestrator.on_undo_plan(7)
        self.assertEqual(self.restored, [])
        self.assertIn(notices.SWITCH_WHILE_RUNNING, self.dock.system)

    def _apply_as(self, plan_id, snapshot):
        self.dock.add_plan_message = lambda lines, applies_itself=False: plan_id
        self.orchestrator.on_confirm_needed([Call()], "")
        self.orchestrator._note_apply_start()
        self.snapshots.append(snapshot)
        self.orchestrator.on_applied([Result(ok=True)])

    def test_undoing_an_earlier_plan_takes_back_the_later_ones_too(self):
        self._apply_as(1, "/tmp/before-a.qgz")
        self.orchestrator.conversation.add("assistant", "Готово.")
        self.orchestrator.conversation.add("user", "и реки")
        self._apply_as(2, "/tmp/before-b.qgz")
        self.orchestrator.on_undo_plan(1)
        self.assertEqual(self.restored, ["/tmp/before-a.qgz"])
        self.assertEqual(sorted(self.dock.undone_plans), [1, 2])
        self.assertEqual(self.dropped, ["/tmp/before-b.qgz"])

    def test_undoing_a_later_stage_of_one_run_keeps_the_earlier_stage(self):
        self._apply_as(1, "/tmp/before-a.qgz")
        self._apply_as(2, "/tmp/before-b.qgz")
        self.orchestrator.on_undo_plan(2)
        self.assertEqual(self.dock.undone_plans, [2])
        self.assertEqual(self.dropped, [])
        self.orchestrator.on_undo_plan(1)
        self.assertEqual(self.restored, ["/tmp/before-b.qgz", "/tmp/before-a.qgz"])
        self.assertEqual(self.dock.undone_plans, [2, 1])

    def test_an_apply_without_a_snapshot_offers_no_undo(self):
        self.orchestrator.on_confirm_needed([Call()], "")
        self.orchestrator._note_apply_start()
        self.orchestrator.on_applied([Result(ok=True)])
        self.assertFalse(self.dock.undoable)


class OutcomeDock(PlanDock):
    def __init__(self):
        super().__init__()
        self.outcomes = []

    def show_outcome(self, kind):
        self.outcomes.append(kind)


class StatusOutcomeTest(unittest.TestCase):
    """The status line under the feed hears how each run stopped working."""

    def setUp(self):
        self.dock = OutcomeDock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.agent = Agent()

    def test_a_question_waits_for_the_user(self):
        self.orchestrator.on_question_asked("Which roads layer?")
        self.assertEqual(self.dock.outcomes, [notices.STATUS_WAITING])

    def test_an_answer_is_done(self):
        self.orchestrator.on_finished("Three layers.")
        self.assertEqual(self.dock.outcomes, [notices.STATUS_DONE])

    def test_an_error_is_failed_and_a_stop_hides_the_line(self):
        self.orchestrator.on_failed("HTTP 500")
        self.orchestrator.on_aborted()
        self.assertEqual(self.dock.outcomes, [notices.STATUS_FAILED, notices.STATUS_HIDDEN])

    def test_a_plan_card_takes_over_and_its_apply_reports(self):
        self.orchestrator.on_confirm_needed([Call()], "")
        self.orchestrator.on_applied([Result(ok=False, payload={"error": "boom"})])
        self.assertEqual(self.dock.outcomes, [notices.STATUS_HIDDEN, notices.STATUS_FAILED])
