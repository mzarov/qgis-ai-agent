import unittest
from types import SimpleNamespace
from unittest import mock

from ai_agent.core.agent import compaction
from ai_agent.core.agent.compaction import COMPACT_REQUEST, COMPACT_SYSTEM, Compactor, estimated_tokens
from ai_agent.core.llm import context_window
from ai_agent.core.orchestrator import compacting
from ai_agent.core.orchestrator.compacting import SessionCompaction
from ai_agent.ui.context_meter import ContextMeter, tokens


class WindowSizeTest(unittest.TestCase):
    def test_a_size_set_by_hand_wins_then_the_detected_one_then_the_name(self):
        with (
            mock.patch.object(context_window, "get_context_window", return_value=50_000),
            mock.patch.object(context_window, "get_detected_context_window", return_value=64_000),
        ):
            self.assertEqual(context_window.window_for("https://x/v1", "gpt-4o"), 50_000)
        with (
            mock.patch.object(context_window, "get_context_window", return_value=0),
            mock.patch.object(context_window, "get_detected_context_window", return_value=64_000),
        ):
            self.assertEqual(context_window.window_for("https://x/v1", "gpt-4o"), 64_000)
        with (
            mock.patch.object(context_window, "get_context_window", return_value=0),
            mock.patch.object(context_window, "get_detected_context_window", return_value=0),
        ):
            self.assertEqual(context_window.window_for("https://x/v1", "openai/gpt-4.1-mini"), 1_047_576)
            self.assertEqual(context_window.window_for("https://x/v1", "my-local-thing"), 128_000)

    def test_a_models_listing_entry_names_its_window_under_several_keys(self):
        self.assertEqual(context_window._window_in({"context_length": 262144}), 262144)
        self.assertEqual(context_window._window_in({"max_model_len": "32768"}), 32768)
        self.assertEqual(context_window._window_in({"name": "x"}), 0)

    def test_auto_compaction_sits_at_ninety_percent(self):
        self.assertEqual(context_window.auto_compact_at(100_000), 90_000)


class CompactorTest(unittest.TestCase):
    def test_the_request_is_the_whole_history_between_the_prompt_and_the_ask(self):
        compactor = Compactor()
        started = {}
        compactor._turn = SimpleNamespace(
            is_running=False,
            start=lambda messages, tools, overrides, on_turn, on_error: started.update(messages=messages, tools=tools),
            release=lambda: None,
        )
        history = [{"role": "user", "content": "раскрась районы"}, {"role": "assistant", "content": "готово"}]
        self.assertTrue(compactor.start(history))
        self.assertEqual(started["messages"][0], {"role": "system", "content": COMPACT_SYSTEM})
        self.assertEqual(started["messages"][1:3], history)
        self.assertEqual(started["messages"][-1]["content"], COMPACT_REQUEST)
        self.assertEqual(started["tools"], [])

    def test_an_empty_answer_is_a_failure_not_an_empty_summary(self):
        compactor = Compactor()
        compactor._turn = SimpleNamespace(release=lambda: None)
        failures: list[str] = []
        compactor.failed.connect(failures.append)
        compactor._on_turn(SimpleNamespace(text="  ", input_tokens=10, output_tokens=0))
        self.assertEqual(failures, [compaction.EMPTY_SUMMARY])

    def test_estimates_count_characters_by_four(self):
        self.assertEqual(estimated_tokens([{"content": "x" * 400}, {"content": "y" * 40}]), 110)

    def test_a_picture_counts_as_a_flat_amount_not_as_its_base64(self):
        picture = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 700_000}}
        message = {"role": "user", "content": [{"type": "text", "text": "x" * 400}, picture]}
        self.assertEqual(estimated_tokens([message]), 100 + compaction.IMAGE_TOKENS)


class Dock:
    def __init__(self):
        self.system: list[str] = []
        self.errors: list[str] = []
        self.context: tuple[int, int, int] | None = None
        self.busy: list[bool] = []
        self.steps: list[tuple[int, bool]] = []

    def add_system_message(self, text):
        self.system.append(text)

    def add_error_message(self, text):
        self.errors.append(text)

    def add_tool_message(self, _text):
        return 0

    def mark_tool_done(self, message_id, ok=True, note=""):
        self.steps.append((message_id, ok))

    def set_busy(self, busy):
        self.busy.append(busy)

    def set_context(self, used, window, spent, turns=0):
        self.context = (used, window, spent, turns)


class SessionCompactionTest(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile

        from ai_agent.core.state.conversation import ConversationState
        from ai_agent.core.state.store import SessionStore

        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.conversation = ConversationState(store=SessionStore(self.root))
        for index in range(6):
            self.conversation.add("user" if index % 2 == 0 else "assistant", "текст " * 200)
        self.dock = Dock()
        patcher = mock.patch.object(SessionCompaction, "window", return_value=10_000)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.compaction = SessionCompaction(self.dock, lambda: self.conversation)
        self.compaction._compactor = mock.MagicMock(is_running=False)
        self.compaction._compactor.start.return_value = True

    def test_compaction_is_needed_only_past_ninety_percent(self):
        self.conversation.set_context(8_999)
        self.assertFalse(self.compaction.needed())
        self.conversation.set_context(9_000)
        self.assertTrue(self.compaction.needed())

    def test_a_finished_compaction_shrinks_the_window_and_then_runs_the_request(self):
        self.conversation.set_context(9_500)
        ran: list[bool] = []
        self.assertTrue(self.compaction.start(after=lambda: ran.append(True)))
        self.compaction._on_finished("Пользователь красил районы.", 9_000, 300)
        self.assertEqual(ran, [True])
        self.assertLess(self.conversation.context_tokens, 9_500)
        self.assertEqual(self.conversation.spent_tokens, 9_300)
        self.assertIn("Пользователь красил районы.", self.conversation.window()[0]["content"])
        self.assertTrue(any(compacting.COMPACTED.split("{0}")[0] in text for text in self.dock.system))
        self.assertEqual(self.dock.busy, [True, False])
        self.assertEqual(self.dock.context[1], 10_000)
        self.assertEqual(self.dock.steps, [(0, True)], "the step settles instead of pulsing on")

    def test_a_failed_compaction_still_lets_the_request_go(self):
        ran: list[bool] = []
        self.compaction.start(after=lambda: ran.append(True))
        self.compaction._on_failed("boom")
        self.assertEqual(ran, [True])
        self.assertIn("boom", self.dock.errors[-1])
        self.assertEqual(self.dock.steps, [(0, False)])


class MeterTest(unittest.TestCase):
    def test_numbers_read_like_claude_code(self):
        self.assertEqual(
            (tokens(950), tokens(21_340), tokens(128_000), tokens(1_000_000)), ("950", "21.3k", "128k", "1M")
        )

    def test_the_ring_fills_with_the_used_share(self):
        from qgis.PyQt.QtWidgets import QWidget

        meter = ContextMeter(QWidget().palette())
        meter.set_numbers(64_000, 128_000, 300_000)
        self.assertAlmostEqual(meter.ring.share, 0.5)
        self.assertIn("51.2k", meter.popup.until.text())


if __name__ == "__main__":
    unittest.main()


class CompactionLifecycleTest(SessionCompactionTest):
    def test_a_summary_for_a_conversation_the_user_left_is_dropped(self):
        ran: list[bool] = []
        self.compaction.start(after=lambda: ran.append(True))
        self.conversation.start_new()
        self.compaction._on_finished("сводка старого разговора", 100, 10)
        self.assertEqual(ran, [])
        self.assertEqual(self.conversation.window(), [])
        self.assertFalse(self.compaction.is_running)

    def test_stop_runs_the_cancel_hook_and_never_the_request(self):
        ran: list[str] = []
        self.compaction.start(after=lambda: ran.append("after"), cancelled=lambda: ran.append("cancelled"))
        self.compaction.cancel()
        self.assertEqual(ran, ["cancelled"])
        self.compaction._compactor.abort.assert_called_once()
        self.assertEqual(self.dock.busy, [True, False])
        self.assertEqual(self.dock.steps, [(0, False)])

    def test_messages_added_while_summarising_stay_in_the_window(self):
        self.compaction.start()
        self.conversation.add("user", "пришло во время сжатия")
        self.compaction._on_finished("сводка", 100, 10)
        self.assertEqual(self.conversation.window()[-1]["content"], "пришло во время сжатия")
        self.assertEqual(len(self.conversation.window()), 2 + 2 + 1)

    def test_a_failure_for_a_conversation_the_user_left_is_not_shown(self):
        ran: list[bool] = []
        self.compaction.start(after=lambda: ran.append(True))
        self.conversation.start_new()
        self.compaction._on_failed("HTTP 500")
        self.assertEqual((ran, self.dock.errors), ([], []))
        self.assertFalse(self.compaction.is_running)

    def test_a_second_start_and_a_refused_one_change_nothing(self):
        self.assertTrue(self.compaction.start())
        self.assertFalse(self.compaction.start())
        self.compaction.cancel()
        self.compaction.cancel()
        self.assertEqual(self.dock.busy, [True, False])
        self.compaction._compactor.start.return_value = False
        self.assertFalse(self.compaction.start())
        self.assertFalse(self.compaction.is_running)

    def test_compacting_an_empty_conversation_by_hand_says_so(self):
        self.conversation.start_new()
        self.assertFalse(self.compaction.start())
        self.assertEqual(self.dock.system, [compacting.NOTHING_TO_COMPACT])
        self.assertFalse(self.compaction.start(after=lambda: None))
        self.assertEqual(len(self.dock.system), 1, "a compaction before a request must stay silent")


class CompactorLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.compactor = Compactor()
        self.turn = mock.MagicMock(is_running=False)
        self.compactor._turn = self.turn

    def test_nothing_is_asked_without_history_or_while_asking(self):
        self.assertFalse(self.compactor.start([]))
        self.turn.is_running = True
        self.assertFalse(self.compactor.start([{"role": "user", "content": "hi"}]))
        self.turn.start.assert_not_called()

    def test_a_transport_error_is_the_failure_and_frees_the_turn(self):
        failures: list[str] = []
        self.compactor.failed.connect(failures.append)
        self.compactor._on_error("HTTP 429")
        self.assertEqual(failures, ["HTTP 429"])
        self.turn.release.assert_called_once_with()

    def test_abort_and_stop_detach_the_answer_first(self):
        self.compactor.abort()
        self.compactor.stop()
        self.assertEqual(self.turn.detach.call_count, 2)
        self.assertEqual([name for name, _args, _kwargs in self.turn.mock_calls][-2:], ["detach", "stop"])


class LoopCountsTest(unittest.TestCase):
    def test_every_turn_is_counted_and_a_silent_server_gets_an_estimate(self):
        from ai_agent.core.agent.loop import AgentLoop

        loop = AgentLoop()
        seen: list[tuple[int, int, bool]] = []
        loop.turn_counted.connect(lambda prompt, completion, first: seen.append((prompt, completion, first)))
        loop._request_estimate = 777
        loop._track_usage(SimpleNamespace(input_tokens=0, output_tokens=0))
        loop._track_usage(SimpleNamespace(input_tokens=1200, output_tokens=40))
        self.assertEqual(seen, [(777, 0, True), (1200, 40, False)])


class DetectionTest(unittest.TestCase):
    def detect(self, url: str, answers: dict[str, dict]) -> tuple[int, list[str]]:
        asked: list[str] = []

        def request(address, _headers, _verify, _feedback, _body=None):
            asked.append(address)
            return answers.get(address, {})

        with (
            mock.patch.object(context_window, "build_request", return_value=(f"{url}/chat/completions", {}, "m1")),
            mock.patch.object(context_window, "_request", side_effect=request),
        ):
            return context_window.detect({"url_override": url}), asked

    def test_an_openai_style_listing_answers_first(self):
        found, asked = self.detect(
            "https://openrouter.ai/api/v1",
            {
                "https://openrouter.ai/api/v1/models": {"data": [{"id": "m0"}, {"id": "m1", "context_length": 262144}]},
            },
        )
        self.assertEqual((found, asked), (262144, ["https://openrouter.ai/api/v1/models"]))

    def test_ollama_answers_with_num_ctx_only(self):
        found, asked = self.detect(
            "http://localhost:11434/v1",
            {
                "http://localhost:11434/api/show": {"parameters": "temperature 0.7\nnum_ctx 32768", "model_info": {}},
            },
        )
        self.assertEqual(found, 32768)
        found, _asked = self.detect(
            "http://localhost:11434/v1",
            {
                "http://localhost:11434/api/show": {"model_info": {"qwen3.context_length": 262144}},
            },
        )
        self.assertEqual(found, 0, "the trained maximum is not the window Ollama runs")

    def test_lm_studio_and_only_the_configured_host(self):
        found, asked = self.detect(
            "http://localhost:1234/v1",
            {
                "http://localhost:1234/api/v0/models/m1": {"max_context_length": 8192},
            },
        )
        self.assertEqual(found, 8192)
        self.assertTrue(all(address.startswith("http://localhost:1234/") for address in asked))
        self.assertNotIn("http://localhost:1234/api/show", asked, "Ollama is asked only on its own port")


class TrimmingTest(unittest.TestCase):
    def test_the_summary_mark_follows_trimming(self):
        from ai_agent.core.state.session import MAX_MESSAGES, Session

        session = Session.create("/p.qgz")
        for index in range(MAX_MESSAGES):
            session.add("user" if index % 2 == 0 else "assistant", str(index))
        session.compact("s", 2)
        before = session.summary_index
        session.add("user", "more")
        session.add("assistant", "more")
        self.assertEqual(session.summary_index, before - 2)
        self.assertEqual(session.messages[session.summary_index]["content"], str(MAX_MESSAGES - 2))

    def test_messages_added_while_the_summary_was_written_stay_after_the_head_is_trimmed(self):
        from ai_agent.core.state.session import MAX_MESSAGES, Session

        session = Session.create("/p.qgz")
        for index in range(MAX_MESSAGES):
            session.add("user" if index % 2 == 0 else "assistant", str(index))
        upto = session.end
        session.add("user", "asked meanwhile")
        session.add("assistant", "answered meanwhile")
        session.compact("s", 0, upto)
        self.assertEqual(
            [message["content"] for message in session.messages[session.summary_index :]],
            ["asked meanwhile", "answered meanwhile"],
        )


class OrchestratorCompactionTest(unittest.TestCase):
    def setUp(self):
        from ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
        from tests.test_orchestrator import Agent, Dock, Iface

        self.dock = Dock()
        self.core = CoreOrchestrator(Iface(), self.dock)
        self.core.agent = Agent()
        self.core.compaction = mock.MagicMock(is_running=True)

    def test_stop_during_compaction_cancels_it_and_leaves_the_agent_alone(self):
        self.core.on_stop()
        self.core.compaction.cancel.assert_called_once()
        self.assertEqual(self.core.agent.aborts, 0)

    def test_switching_conversations_cancels_a_running_compaction(self):
        self.core.on_new_session()
        self.core.compaction.cancel.assert_called()

    def test_compact_by_hand_waits_for_a_pending_plan(self):
        self.core.compaction.is_running = False
        self.core.agent.has_pending_writes = True
        self.core.on_compact()
        self.core.compaction.start.assert_not_called()
