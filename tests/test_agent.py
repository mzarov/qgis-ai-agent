import unittest

from qgis_ai_agent.core.agent import batch as batch_module
from qgis_ai_agent.core.agent.batch import WriteBatch
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
        result = self.loop._dispatch(
            call("run_processing", algorithm_id="native:buffer", parameters={})
        )
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
        self.assertIs(first, second)
        self.assertEqual(len(self.batch.pending()), 1)

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


if __name__ == "__main__":
    unittest.main()
