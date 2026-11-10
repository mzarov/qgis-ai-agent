import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from ai_agent.core.agent import apply_run as apply_run_module
from ai_agent.core.agent import batch as batch_module
from ai_agent.core.agent import batch_apply as batch_apply_module
from ai_agent.core.agent import loop as loop_module
from ai_agent.core.agent import run_journal
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.failure_kinds import AUTH, TurnFailure
from ai_agent.core.llm.turns import PROTOCOL_NATIVE, ModelTurn, ToolCall
from ai_agent.core.orchestrator import plans as plans_module
from ai_agent.core.orchestrator import rewind as rewind_module
from ai_agent.core.orchestrator.orchestrator import CoreOrchestrator
from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.state.store import SessionStore
from tests.test_orchestrator import Iface

REQUEST = SimpleNamespace(messages=[], tool_schemas=[], overrides={}, protocol=PROTOCOL_NATIVE)
UNDO_TOOL = "undo_last_apply"
LEAKY = "Error transferring https://bob:hunter2@llm.example.com/v1/chat?key=AIzaSECRET123456 - Bad Gateway"


class Turns:
    def __init__(self):
        self.callbacks = None

    @property
    def is_running(self):
        return self.callbacks is not None

    def start(self, messages, schemas, overrides, *callbacks):
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


class Dock:
    ANSWERS = {"confirm_data_sharing": True, "confirm_destructive": True, "keep_stream": "", "context_mention": ""}

    def __init__(self):
        self.log = []
        self._entries = 0

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.log.append((name, args))
            if name.startswith("add_"):
                self._entries += 1
                return self._entries
            if name == "take_attachments":
                return []
            return self.ANSWERS.get(name, False if name == "finish_stream" else 0)

        return record

    def calls(self, name):
        return [args for called, args in self.log if called == name]


class Executor:
    def __init__(self, undo):
        self.ran: list[str] = []
        self._undo = undo

    @staticmethod
    def start(tool_call, done):
        return None

    def run(self, tool_call):
        self.ran.append(tool_call.name)
        if tool_call.name == UNDO_TOOL:
            self._undo()
        return ToolResult(call=tool_call, payload={"ok": True})

    @staticmethod
    def queued(tool_call):
        return ToolResult(call=tool_call, payload={"status": "queued"})


def call(name, identifier, **arguments):
    return ToolCall(id=identifier, name=name, arguments=arguments)


class RunFlowCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.snapshots: list[str] = []
        self.taken = 0
        for target, name, value in (
            (loop_module, "build_step_request", lambda *args, **kwargs: REQUEST),
            (batch_module, "prepare_tool_call", lambda name, arguments: dict(arguments)),
            (batch_module, "pin_layer_references", lambda arguments: arguments),
            (batch_module, "validate_public_layer_references", lambda arguments: arguments),
            (batch_apply_module, "take_snapshot", self._take),
            (batch_apply_module, "project_identity", lambda project: "project"),
            (apply_run_module, "project_identity", lambda project: "project"),
            (apply_run_module, "layer_pin_error", lambda arguments: ""),
            (apply_run_module, "layer_names_by_id", lambda: {}),
            (rewind_module, "last_snapshot", self._last),
            (rewind_module, "snapshot_exists", lambda path: path in self.snapshots),
            (rewind_module, "drop_snapshot", self._drop),
            (rewind_module, "restore_snapshot", self._restore),
            (plans_module, "last_snapshot", self._last),
            (plans_module, "get_verify_after_apply", lambda: False),
        ):
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.dock = Dock()
        self.orchestrator = CoreOrchestrator(Iface(), self.dock)
        self.orchestrator.conversation = ConversationState(store=SessionStore(self.root))
        self.orchestrator._confirm_first_send = lambda *endpoint: True
        self.orchestrator.compaction = mock.MagicMock(is_running=False)
        self.orchestrator.compaction.needed.return_value = False
        self.turns = Turns()
        agent = self.orchestrator.agent
        agent._turn = self.turns
        self.executor = Executor(lambda: self._restore(self._last()))
        agent._executor = self.executor
        agent._batch._executor = self.executor

    def _take(self):
        self.taken += 1
        self.snapshots.append(f"S{self.taken}")
        return self.snapshots[-1]

    def _last(self):
        return self.snapshots[-1] if self.snapshots else ""

    def _drop(self, path):
        if path in self.snapshots:
            self.snapshots.remove(path)

    def _restore(self, path):
        self._drop(path)
        return {}

    def plan(self, prompt, tool="set_opacity"):
        self.orchestrator.on_prompt(prompt)
        self.turns.answer(ModelTurn(tool_calls=[call(tool, f"{tool}-{prompt}", layer_name="roads")]))
        self.turns.answer(ModelTurn(text="ready"))
        return self.orchestrator._plan_message_id

    def apply(self, prompt, tool="set_opacity"):
        card = self.plan(prompt, tool)
        self.orchestrator.on_confirm_plan()
        return card


class UndoQueuedByTheModelTest(RunFlowCase):
    def test_the_snapshot_an_undo_uncovers_stays_with_the_plan_that_took_it(self):
        first = self.apply("style roads")
        self.apply("label roads")
        undo = self.apply("undo that", UNDO_TOOL)

        self.assertEqual(self.snapshots, ["S1"])
        self.assertEqual([item.snapshot for item in self.orchestrator._checkpoints], ["S1", "S2"])
        self.assertEqual(self.orchestrator._plan_snapshots.get(first), "S1")
        self.assertNotIn(undo, self.orchestrator._plan_snapshots)
        self.assertEqual(self.dock.calls("mark_plan_completed")[-1], (undo, False))
        places = [item.message for item in self.orchestrator._checkpoints]
        self.assertIsNone(self.orchestrator.checkpoint_for(places[-1] + 1), "the undo request has no checkpoint")

    def test_a_plan_after_the_undo_gets_its_own_checkpoint(self):
        self.apply("style roads")
        self.apply("label roads")
        self.apply("undo that", UNDO_TOOL)
        again = self.apply("label roads again")
        self.assertEqual(self.orchestrator._plan_snapshots.get(again), "S3")
        self.assertEqual(self.orchestrator._checkpoints[-1].snapshot, "S3")


class RetryAfterSettingsTest(RunFlowCase):
    def offered(self):
        return len(self.dock.calls("offer_retry"))

    def test_a_refused_key_is_offered_retry_once_the_settings_are_saved(self):
        self.orchestrator.on_prompt("add a buffer layer")
        self.turns.fail(TurnFailure("HTTP 401", AUTH))
        self.assertFalse(self.dock.calls("add_run_failure")[-1][-1])
        self.orchestrator.on_settings_saved()
        self.assertEqual(self.offered(), 1)

    def test_a_failed_check_of_applied_work_is_never_retried(self):
        self.apply("add a buffer layer")
        self.orchestrator.agent.start("check it", [], verification=True)
        self.turns.fail(TurnFailure("HTTP 401", AUTH))
        self.orchestrator.on_settings_saved()
        self.assertEqual(self.offered(), 0)

    def test_steps_applied_after_the_failure_take_the_retry_away(self):
        self.orchestrator.on_prompt("add a buffer layer")
        self.turns.answer(ModelTurn(tool_calls=[call("set_opacity", "w1", layer_name="roads")]))
        self.turns.fail(TurnFailure("HTTP 401", AUTH))
        self.orchestrator.on_confirm_plan()
        self.assertEqual(self.executor.ran, ["set_opacity"])
        self.orchestrator.on_settings_saved()
        self.assertEqual(self.offered(), 0)


class JournalTest(RunFlowCase):
    def test_a_failure_is_written_without_the_login_or_the_key_in_its_address(self):
        written = []
        for target, name, value in (
            (run_journal, "get_write_run_journal", lambda: True),
            (run_journal, "record_run", lambda prompt, entries, outcome, applied, requests: written.append(outcome)),
        ):
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.orchestrator.on_prompt("stage it")
        self.turns.answer(
            ModelTurn(tool_calls=[call("set_opacity", "w1", layer_name="roads"), call("apply_now", "a1", reason="r")])
        )
        self.orchestrator.on_confirm_plan()
        self.turns.fail(LEAKY)
        self.assertEqual(len(written), 1)
        self.assertIn("https://llm.example.com/v1/chat", written[0])
        for secret in ("hunter2", "AIzaSECRET123456", "bob"):
            self.assertNotIn(secret, written[0])


class PathPromptTest(RunFlowCase):
    def test_a_request_that_opens_with_a_path_is_sent_as_it_is(self):
        text = "/Users/me/data/roads.gpkg — add this file as a layer"
        self.orchestrator.on_prompt(text)
        self.assertIsNotNone(self.turns.callbacks)
        self.assertEqual(self.orchestrator.conversation.messages[-1]["content"], text)

    def test_an_unknown_command_is_still_refused_with_the_list(self):
        self.orchestrator.on_prompt("/nosuchskill do it")
        self.assertIsNone(self.turns.callbacks)
        self.assertIn("/style", self.dock.calls("add_system_message")[-1][0])


class StagedRunCountTest(RunFlowCase):
    def counted(self):
        noted = self.orchestrator.usage.note.call_args_list
        return [(entry.args[0], entry.args[1]) for entry in noted if entry.args[0] in ("outcomes", "steps")]

    def test_a_staged_run_is_counted_when_it_ends_not_at_its_first_pause(self):
        usage = self.orchestrator.usage
        usage.note = mock.Mock()
        self.orchestrator.on_prompt("stage it")
        self.turns.answer(
            ModelTurn(tool_calls=[call("set_opacity", "w1", layer_name="roads"), call("apply_now", "a1", reason="r")])
        )
        self.assertEqual(self.counted(), [])
        self.orchestrator.on_confirm_plan()
        self.turns.answer(ModelTurn(tool_calls=[call("list_layers", "r1")]))
        self.turns.fail(TurnFailure("HTTP 500", "http_500"))
        self.assertEqual(self.counted(), [("outcomes", "failed"), ("steps", "s2_3")])

    def test_a_plan_offered_at_the_end_closes_the_run(self):
        self.orchestrator.usage.note = mock.Mock()
        self.plan("style roads")
        self.assertEqual(self.counted(), [("outcomes", "answered"), ("steps", "s2_3")])


if __name__ == "__main__":
    unittest.main()
