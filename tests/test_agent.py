import unittest

from qgis_ai_agent.core.agent import batch as batch_module
from qgis_ai_agent.core.agent import executor as executor_module
from qgis_ai_agent.core.agent.batch import WriteBatch
from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.agent.loop import AgentLoop
from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.registry import ALL_TOOLS, get_tool_by_name
from qgis_ai_agent.skills.registry import SKILL_REGISTRY


class FakeExecutor:
    def __init__(self):
        self.ran = []

    def run(self, call):
        if get_tool_by_name(call.name) is None:
            return ToolResult.failure(call, "неизвестный тул")
        self.ran.append(call.name)
        return ToolResult(call=call, ok=True, payload={"fake": True})

    @staticmethod
    def queued(call):
        return ToolResult(call=call, ok=True, payload={"status": "queued"})


def call(tool, **arguments):
    return ToolCall(id="c", name=tool, arguments=arguments)


class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.executor = FakeExecutor()
        self.loop._executor = self.executor
        self.loop._batch._executor = self.executor
        self.loop._loaded_skills = ["inspect"]

    def test_read_tool_runs_at_once(self):
        result = self.loop._dispatch(call("list_layers"))
        self.assertTrue(result.ok)
        self.assertEqual(self.executor.ran, ["list_layers"])
        self.assertFalse(self.loop.has_pending_writes)

    def test_unknown_tool_is_an_error_not_a_crash(self):
        self.assertFalse(self.loop._dispatch(call("нет_такого")).ok)

    def test_load_skill_adds_domain(self):
        result = self.loop._dispatch(call("load_skill", name="processing"))
        self.assertTrue(result.ok)
        self.assertIn("processing", self.loop._loaded_skills)
        self.assertIn("run_processing", result.payload["tools"])

    def test_unknown_skill_lists_available(self):
        result = self.loop._dispatch(call("load_skill", name="мусор"))
        self.assertFalse(result.ok)
        offered = result.payload["available"]
        self.assertEqual(offered, SKILL_REGISTRY.names())
        self.assertIn("inspect", offered)

    def test_invalid_write_is_rejected_before_the_queue(self):
        result = self.loop._dispatch(call("run_processing", algorithm_id="native:buffer", parameters={}))
        self.assertFalse(result.ok)
        self.assertIn("arguments_sent", result.payload)
        self.assertFalse(self.loop.has_pending_writes)
        self.assertEqual(self.executor.ran, [])

    def test_no_write_ever_runs_without_confirmation(self):
        for tool in ALL_TOOLS:
            if not tool.is_read_only:
                self.loop._dispatch(call(tool.name))
        for name in self.executor.ran:
            self.assertTrue(get_tool_by_name(name).is_read_only, name)


class ExecutorLogPrivacyTest(unittest.TestCase):
    def test_failure_log_does_not_include_arguments_or_exception_text(self):
        saved_execute = executor_module.execute_tool
        saved_log = executor_module.QgsMessageLog
        messages = []
        executor_module.execute_tool = lambda name, arguments: (_ for _ in ()).throw(ValueError("sentinel-secret"))
        executor_module.QgsMessageLog = type(
            "MessageLog",
            (),
            {"logMessage": staticmethod(lambda message, *args: messages.append(message))},
        )
        try:
            result = ToolExecutor().run(
                ToolCall(id="secret-call", name="list_layers", arguments={"token": "sentinel-secret"})
            )
        finally:
            executor_module.execute_tool = saved_execute
            executor_module.QgsMessageLog = saved_log
        self.assertFalse(result.ok)
        self.assertNotIn("sentinel-secret", "\n".join(messages))
        self.assertIn("secret-call", messages[0])


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.executor = FakeExecutor()
        self.loop._batch._executor = self.executor

    def test_cancel_empties_the_queue(self):
        self.loop._batch._calls = [call("run_processing")]
        self.loop.cancel_pending()
        self.assertFalse(self.loop.has_pending_writes)

    def test_confirm_on_empty_queue_does_nothing(self):
        self.loop.confirm_pending()
        self.assertEqual(self.executor.ran, [])


class BatchDedupTest(unittest.TestCase):
    def setUp(self):
        self.batch = WriteBatch(FakeExecutor())
        self._saved = batch_module.prepare_tool_call
        batch_module.prepare_tool_call = lambda name, params: params

    def tearDown(self):
        batch_module.prepare_tool_call = self._saved

    def test_identical_calls_collapse(self):
        first = self.batch.add(call("set_opacity", layer_name="Дороги", opacity=0.5))
        second = self.batch.add(call("set_opacity", layer_name="Дороги", opacity=0.5))
        self.assertIsNot(first, second)
        self.assertEqual(len(self.batch.pending()), 1)

    def test_duplicate_acknowledgements_keep_each_model_call_id(self):
        first = ToolCall(id="write_1", name="set_opacity", arguments={"layer_name": "Дороги", "opacity": 0.5})
        second = ToolCall(id="write_2", name="set_opacity", arguments={"layer_name": "Дороги", "opacity": 0.5})
        self.assertEqual(self.batch.add(first).id, "write_1")
        self.assertEqual(self.batch.add(second).id, "write_2")
        self.assertEqual([item.id for item in self.batch.pending()], ["write_1"])

    def test_different_arguments_stay_separate(self):
        self.batch.add(call("set_opacity", layer_name="Дороги", opacity=0.5))
        self.batch.add(call("set_opacity", layer_name="Дороги", opacity=0.9))
        self.assertEqual(len(self.batch.pending()), 2)

    def test_argument_order_does_not_split_a_duplicate(self):
        self.batch.add(call("set_opacity", layer_name="Дороги", opacity=0.5))
        self.batch.add(call("set_opacity", opacity=0.5, layer_name="Дороги"))
        self.assertEqual(len(self.batch.pending()), 1)

    def test_different_tools_stay_separate(self):
        self.batch.add(call("set_opacity", layer_name="Дороги", opacity=0.5))
        self.batch.add(call("set_symbol", layer_name="Дороги", opacity=0.5))
        self.assertEqual(len(self.batch.pending()), 2)

    def test_duplicate_is_applied_once(self):
        self.batch.add(call("set_opacity", layer_name="Дороги", opacity=0.5))
        self.batch.add(call("set_opacity", layer_name="Дороги", opacity=0.5))
        results = self.batch.apply(lambda item: None, lambda item, result: None)
        self.assertEqual(len(results), 1)

    def test_undo_cannot_be_mixed_with_other_writes(self):
        self.batch.add(call("undo_last_apply"))
        with self.assertRaisesRegex(ValueError, "by itself"):
            self.batch.add(call("set_opacity", layer_name="roads", opacity=0.5))


class BatchFailFastTest(unittest.TestCase):
    def setUp(self):
        class FailingExecutor(FakeExecutor):
            def run(inner_self, item):
                inner_self.ran.append(item.name)
                if item.name == "set_symbol":
                    return ToolResult.failure(item, "style provider failed")
                return ToolResult(call=item, ok=True, payload={"fake": True})

        self.executor = FailingExecutor()
        self.batch = WriteBatch(self.executor)
        self._saved = batch_module.prepare_tool_call
        batch_module.prepare_tool_call = lambda name, params: params

    def tearDown(self):
        batch_module.prepare_tool_call = self._saved

    def test_later_dependent_steps_are_skipped_after_first_failure(self):
        self.batch.add(ToolCall(id="one", name="set_opacity", arguments={"opacity": 0.5}))
        self.batch.add(ToolCall(id="two", name="set_symbol", arguments={"color": "#ff0000"}))
        self.batch.add(ToolCall(id="three", name="configure_layer", arguments={"visible": True}))
        finished = []

        results = self.batch.apply(lambda item: None, lambda item, result: finished.append((item.id, result.ok)))

        self.assertEqual(self.executor.ran, ["set_opacity", "set_symbol"])
        self.assertEqual([result.ok for result in results], [True, False, False])
        self.assertEqual(results[2].payload["status"], "skipped")
        self.assertEqual(results[2].payload["blocked_by"], {"id": "two", "tool": "set_symbol"})
        self.assertEqual(finished, [("one", True), ("two", False), ("three", False)])

    def test_skipped_sensitive_tool_keeps_egress_provenance(self):
        self.batch.add(ToolCall(id="fail", name="set_symbol", arguments={}))
        self.batch.add(ToolCall(id="sensitive", name="run_processing", arguments={}))
        results = self.batch.apply(lambda item: None, lambda item, result: None)
        self.assertFalse(results[1].ok)
        self.assertEqual(results[1].egress, "feature_values")

    def test_project_change_stops_the_current_and_later_steps(self):
        self.batch.add(ToolCall(id="one", name="set_opacity", arguments={}))
        self.batch.add(ToolCall(id="two", name="set_symbol", arguments={}))
        self.batch.add(ToolCall(id="three", name="configure_layer", arguments={}))
        saved_identity = batch_module.project_identity
        identities = iter(("project-a", "project-b"))
        batch_module.project_identity = lambda project: next(identities)
        try:
            results = self.batch.apply(
                lambda item: None,
                lambda item, result: None,
                expected_project_identity="project-a",
            )
        finally:
            batch_module.project_identity = saved_identity
        self.assertEqual(self.executor.ran, ["set_opacity"])
        self.assertTrue(results[0].ok)
        self.assertIn("project changed", results[1].payload["error"].lower())
        self.assertEqual(results[2].payload["status"], "skipped")

    def test_batch_remains_busy_until_every_step_finishes(self):
        self.batch.add(ToolCall(id="one", name="set_opacity", arguments={}))
        applying = []
        self.batch.apply(
            lambda item: applying.append(bool(self.batch) and self.batch.is_applying),
            lambda item, result: applying.append(bool(self.batch) and self.batch.is_applying),
        )
        self.assertEqual(applying, [True, True])
        self.assertFalse(self.batch)


if __name__ == "__main__":
    unittest.main()
