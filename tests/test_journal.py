import os
import shutil
import tempfile
import unittest

from ai_agent.core.agent import loop as loop_module
from ai_agent.core.agent.journal import render_journal, write_journal
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.transcript import ToolResult, Transcript
from ai_agent.core.llm.transport import ModelTurn, ToolCall


def entries():
    transcript = Transcript()
    transcript.add_user("скачай кафе")
    turn = ModelTurn(text="Сейчас скачаю.", tool_calls=[ToolCall(id="c1", name="download_osm")])
    transcript.add_turn(turn)
    ok = ToolResult(call=ToolCall(id="c1", name="download_osm"), payload={"total_features": 131})
    bad = ToolResult.failure(ToolCall(id="c2", name="set_symbol"), "no such colour")
    transcript.add_results([ok, bad], "native")
    return transcript.entries


class RenderTest(unittest.TestCase):
    def test_the_journal_tells_the_whole_story(self):
        text = render_journal("скачай кафе", entries(), "Готово: кафе на карте.", 2)
        self.assertIn("**Request:** скачай кафе", text)
        self.assertIn("**agent:** Сейчас скачаю.", text)
        self.assertIn("`download_osm` [ok]", text)
        self.assertIn("`set_symbol` [failed] — no such colour", text)
        self.assertIn("**Applied steps:** 2", text)
        self.assertIn("**Outcome:** Готово", text)

    def test_long_texts_are_shortened(self):
        text = render_journal("x" * 1000, [], "y" * 1000, 0)
        self.assertEqual(text.count("…"), 2)


class WriteTest(unittest.TestCase):
    def test_the_file_lands_in_the_folder(self):
        folder = tempfile.mkdtemp()
        try:
            path = write_journal("# j", folder)
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith(".md"))
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "# j")
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class LoopJournalTest(unittest.TestCase):
    def setUp(self):
        self.paths = []
        self.saved = loop_module.record_run
        loop_module.record_run = (
            lambda prompt, entries, outcome, applied: self.paths.append((prompt, applied)) or "/tmp/run_x.md"
        )
        self.loop = AgentLoop()
        self.loop._prompt = "скачай кафе"
        self.emitted = []
        self.loop.journal_written.connect(self.emitted.append)

    def tearDown(self):
        loop_module.record_run = self.saved

    def test_a_run_without_applies_writes_nothing(self):
        self.loop._applied_steps = 0
        self.loop._write_journal("готово")
        self.assertEqual(self.paths, [])
        self.assertEqual(self.emitted, [])

    def test_a_run_with_applies_writes_and_announces(self):
        self.loop._applied_steps = 3
        self.loop._write_journal("готово")
        self.assertEqual(self.paths, [("скачай кафе", 3)])
        self.assertEqual(self.emitted, ["/tmp/run_x.md"])


if __name__ == "__main__":
    unittest.main()
