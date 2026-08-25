import unittest

from qgis_ai_agent.core.agent.loop import AgentLoop
from qgis_ai_agent.core.agent.transcript import ToolResult
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.registry import ALL_TOOLS, get_tool_by_name


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
        self.assertEqual(result.payload["available"], ["inspect", "processing", "style"])

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


if __name__ == "__main__":
    unittest.main()
