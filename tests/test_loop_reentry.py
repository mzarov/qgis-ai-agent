import unittest
from types import SimpleNamespace
from unittest import mock

from ai_agent.core.agent import loop as loop_module
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.prompts import APPLY_NOW_TOOL, ASK_USER_TOOL
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.failure_kinds import OTHER
from ai_agent.core.llm.turns import PROTOCOL_JSON, PROTOCOL_NATIVE, ModelTurn, ToolCall

REQUEST = SimpleNamespace(messages=[], tool_schemas=[], overrides={}, protocol=PROTOCOL_NATIVE)


class Turns:
    def __init__(self):
        self.started = 0
        self.callbacks = None

    @property
    def is_running(self):
        return self.callbacks is not None

    def start(self, messages, schemas, overrides, *callbacks):
        self.started += 1
        self.callbacks = callbacks

    def release(self):
        self.callbacks = None

    def detach(self, *callbacks):
        self.callbacks = None

    def stop(self):
        self.callbacks = None

    def answer(self, turn):
        self.callbacks[0](turn)

    def fail(self, message):
        self.callbacks[1](message)


class Executor:
    def __init__(self, during=None):
        self.ran = []
        self._during = during

    @staticmethod
    def start(call, done):
        return None

    def run(self, call):
        self.ran.append(call.name)
        if self._during is not None:
            self._during()
        return ToolResult(call=call, payload={"layers": []})


def call(name, **arguments):
    return ToolCall(id=f"{name}-1", name=name, arguments=arguments)


class LoopCase(unittest.TestCase):
    def setUp(self):
        request = mock.patch.object(loop_module, "build_step_request", return_value=REQUEST)
        request.start()
        self.addCleanup(request.stop)
        self.loop = AgentLoop()
        self.turns = Turns()
        self.loop._turn = self.turns
        self.use_executor(Executor())
        self.finished, self.failed, self.questions, self.cards, self.aborted = [], [], [], [], []
        self.loop.finished.connect(self.finished.append)
        self.loop.failed.connect(self.failed.append)
        self.loop.question_asked.connect(self.questions.append)
        self.loop.confirm_needed.connect(lambda calls, text, auto: self.cards.append((list(calls), auto)))
        self.loop.aborted.connect(lambda: self.aborted.append(True))
        self.assertTrue(self.loop.start("Look at the project"))

    def use_executor(self, executor):
        self.executor = executor
        self.loop._executor = executor
        self.loop._batch._executor = executor

    def stop_on(self, signal, when=lambda *args: True):
        pressed = []

        def press(*args):
            if when(*args) and not pressed:
                pressed.append(True)
                self.loop.abort()

        signal.connect(press)


class StopInsideASignalTest(LoopCase):
    def test_stop_while_the_preamble_shows_runs_no_tool_and_asks_nothing_more(self):
        self.stop_on(self.loop.preamble)
        self.turns.answer(ModelTurn(text="Let me look at the layers.", tool_calls=[call("list_layers")]))
        self.assertEqual(self.executor.ran, [])
        self.assertEqual(self.turns.started, 1)
        self.assertEqual(self.aborted, [True])

    def test_stop_while_a_read_runs_skips_the_rest_of_the_turn(self):
        self.use_executor(Executor(during=self.loop.abort))
        self.turns.answer(ModelTurn(tool_calls=[call("list_layers"), call("get_project_info")]))
        self.assertEqual(self.executor.ran, ["list_layers"])
        self.assertEqual(self.turns.started, 1)
        self.assertFalse([entry for entry in self.loop._transcript.entries if entry["kind"] == "results"])

    def test_stop_while_the_reasoning_replays_keeps_the_answer_out(self):
        self.stop_on(self.loop.thinking_chunk)
        self.turns.answer(ModelTurn(text="Two layers.", thinking="The project has two layers."))
        self.assertEqual(self.finished, [])
        self.assertFalse([entry for entry in self.loop._transcript.entries if entry["kind"] == "turn"])

    def test_stop_while_the_tokens_are_counted_keeps_the_answer_out(self):
        self.stop_on(self.loop.turn_counted)
        self.turns.answer(ModelTurn(text="Two layers.", input_tokens=900, output_tokens=12))
        self.assertEqual(self.finished, [])

    def test_stop_while_a_protocol_retry_is_counted_sends_nothing_more(self):
        self.stop_on(self.loop.turn_counted)
        self.turns.answer(ModelTurn(text='{"text": "hi"}', protocol=PROTOCOL_JSON))
        self.assertEqual(self.turns.started, 1)

    def test_stop_while_a_nudged_announcement_shows_adds_no_note(self):
        self.stop_on(self.loop.preamble)
        self.turns.answer(ModelTurn(text="I'll load the style tools now."))
        users = [entry for entry in self.loop._transcript.entries if entry["kind"] == "user"]
        self.assertEqual(len(users), 1, "the nudge note was added after the stop")
        self.assertEqual(self.turns.started, 1)


class StopAsTheRunWindsDownTest(LoopCase):
    def setUp(self):
        super().setUp()
        self.stop_on(self.loop.busy_changed, when=lambda busy: not busy)

    def test_a_final_answer_is_not_shown(self):
        self.turns.answer(ModelTurn(text="Two layers."))
        self.assertEqual(self.finished, [])

    def test_a_question_is_not_asked(self):
        self.turns.answer(ModelTurn(tool_calls=[call(ASK_USER_TOOL, question="Which layer?")]))
        self.assertEqual(self.questions, [])
        self.assertFalse(self.loop.is_awaiting_answer)

    def test_a_stage_is_not_offered(self):
        self.loop._batch._calls.append(call("set_opacity", layer_name="roads", opacity=0.5))
        self.turns.answer(ModelTurn(tool_calls=[call(APPLY_NOW_TOOL, reason="first part")]))
        self.assertEqual(self.cards, [])
        self.assertFalse(self.loop.has_pending_writes)

    def test_a_failure_is_not_reported(self):
        self.turns.fail("HTTP 500")
        self.assertEqual(self.failed, [])


class AnswerTest(LoopCase):
    def test_a_stop_as_the_answer_is_taken_sends_nothing(self):
        self.turns.answer(ModelTurn(tool_calls=[call(ASK_USER_TOOL, question="Which layer?")]))
        self.assertEqual(self.questions, ["Which layer?"])
        self.stop_on(self.loop.busy_changed, when=lambda busy: busy)
        self.assertTrue(self.loop.answer("roads"))
        self.assertEqual(self.turns.started, 1)

    def test_an_answer_resumes_the_same_run(self):
        self.turns.answer(ModelTurn(tool_calls=[call(ASK_USER_TOOL, question="Which layer?")]))
        self.assertTrue(self.loop.answer("roads"))
        self.assertEqual(self.turns.started, 2)
        self.assertEqual(self.loop._transcript.entries[-1], {"kind": "user", "text": "roads", "images": []})


class RequestFailureTest(LoopCase):
    def test_a_request_that_cannot_be_built_fails_the_run_and_keeps_the_plan(self):
        self.loop._batch._calls.append(call("set_opacity", layer_name="roads", opacity=0.5))
        with mock.patch.object(loop_module, "build_step_request", side_effect=ValueError("schema too large")):
            self.loop._request_step()
        self.assertEqual(self.failed, ["schema too large"])
        self.assertEqual(self.loop.failure_kind, OTHER)
        self.assertEqual([(len(calls), auto) for calls, auto in self.cards], [(1, False)])
        self.assertEqual(self.turns.started, 1)
        self.assertFalse(self.loop.is_running)

    def test_a_failure_from_an_old_run_is_ignored(self):
        old_fail = self.turns.callbacks[1]
        self.loop.abort()
        self.assertTrue(self.loop.start("Another question"))
        old_fail("HTTP 500")
        self.assertEqual(self.failed, [])
        self.assertTrue(self.loop.is_running)


if __name__ == "__main__":
    unittest.main()
