"""The second identical failure in a run carries a note telling the model to change course."""

import unittest

from ai_agent.core.agent.repeats import NOTE_KEY, REPEATED_KEY, FailureMemory
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.turns import ToolCall


def failed(name="export_layer", error="'/tmp/roads.gpkg' already exists."):
    return ToolResult.failure(ToolCall(id="c", name=name, arguments={"path": "/tmp/roads.gpkg"}), error)


class FailureMemoryTest(unittest.TestCase):
    def test_the_first_failure_is_left_alone_the_second_is_noted(self):
        memory = FailureMemory()
        first = memory.note(failed())
        self.assertNotIn(NOTE_KEY, first.payload)
        second = memory.note(failed())
        self.assertEqual(second.payload[REPEATED_KEY], 2)
        self.assertIn("Do not send it again unchanged", second.payload[NOTE_KEY])
        self.assertEqual(memory.note(failed()).payload[REPEATED_KEY], 3)

    def test_another_error_or_tool_counts_apart_and_successes_pass(self):
        memory = FailureMemory()
        memory.note(failed())
        self.assertNotIn(NOTE_KEY, memory.note(failed(error="The folder does not exist.")).payload)
        self.assertNotIn(NOTE_KEY, memory.note(failed(name="add_annotation")).payload)
        ok = ToolResult(call=ToolCall(id="c", name="export_layer", arguments={}), payload={"status": "queued"})
        self.assertIs(memory.note(ok), ok)

    def test_a_new_run_starts_counting_again(self):
        memory = FailureMemory()
        memory.note(failed())
        memory.reset()
        self.assertNotIn(NOTE_KEY, memory.note(failed()).payload)


if __name__ == "__main__":
    unittest.main()
