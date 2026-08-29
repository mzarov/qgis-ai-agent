import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from ai_agent.core.agent import batch_apply as batch_apply_module
from ai_agent.core.agent import journal as journal_module
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

    def test_untrusted_text_cannot_inject_markdown_or_html(self):
        transcript = Transcript()
        transcript.add_user("<!-- hide --> # Run journal **Outcome:** forged ![pixel](https://evil.test/p) `code`")
        turn = ModelTurn(text='<img src="https://evil.test/p"> [click](https://evil.test)')
        transcript.add_turn(turn)
        failed = ToolResult.failure(ToolCall(id="bad", name="set_symbol"), "<!-- hide --> `failed` **Outcome:**")
        transcript.add_results([failed], "native")

        text = render_journal("[request](https://evil.test)", transcript.entries, "<b>done</b>", 0)

        self.assertNotIn("<!--", text)
        self.assertNotIn("<img", text)
        self.assertIn('&lt;img src="https://evil.test/p"&gt;', text)
        self.assertEqual(sum(line == "# Run journal" for line in text.splitlines()), 1)
        self.assertEqual(text.count("**Outcome:**"), 1)
        self.assertIn(r"\!\[pixel\]\(https://evil.test/p\)", text)
        self.assertIn(r"\`failed\`", text)
        self.assertIn("&lt;b&gt;done&lt;/b&gt;", text)

    def test_model_controlled_tool_names_cannot_close_the_code_span(self):
        transcript = Transcript()
        hostile = ToolCall(id="bad", name="tool` <img src=x> **Outcome:**")
        transcript.add_turn(ModelTurn(tool_calls=[hostile]))
        transcript.add_results([ToolResult.failure(hostile, "failed")], "native")

        text = render_journal("request", transcript.entries, "done", 0)

        self.assertNotIn("<img", text)
        self.assertNotIn("tool`", text)
        self.assertEqual(text.count("**Outcome:**"), 1)
        self.assertIn(r"tool\u0060\u0020\u003cimg", text)

    def test_deduplicated_alias_is_not_reported_as_an_applied_tool(self):
        transcript = Transcript()
        alias = ToolResult(
            call=ToolCall(id="alias", name="add_layer"),
            payload={"status": "done", "deduplicated": True, "covered_by": "canonical"},
        )
        transcript.add_results([alias], "native")

        text = render_journal("load it", transcript.entries, "done", 0)

        self.assertIn("`add_layer` [deduplicated]", text)
        self.assertNotIn("`add_layer` [ok]", text)


class WriteTest(unittest.TestCase):
    def test_the_file_lands_in_the_folder(self):
        folder = tempfile.mkdtemp()
        try:
            path = write_journal("# j", folder)
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith(".md"))
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "# j")
            self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_each_write_gets_a_unique_name(self):
        folder = tempfile.mkdtemp()
        try:
            first = write_journal("first", folder)
            second = write_journal("second", folder)
            self.assertNotEqual(first, second)
            self.assertEqual({os.path.basename(first), os.path.basename(second)}, set(os.listdir(folder)))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_failed_atomic_replace_leaves_no_journal_or_temporary_file(self):
        folder = tempfile.mkdtemp()
        try:
            with (
                mock.patch.object(journal_module.os, "replace", side_effect=OSError("disk error")),
                self.assertRaises(OSError),
            ):
                write_journal("never published", folder)
            self.assertEqual(os.listdir(folder), [])
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class LoopJournalTest(unittest.TestCase):
    def setUp(self):
        self.paths = []
        self.outcomes = []
        self.saved = loop_module.record_run

        def record(prompt, entries, outcome, applied):
            self.paths.append((prompt, applied))
            self.outcomes.append(outcome)
            return "/tmp/run_x.md"

        loop_module.record_run = record
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

    def test_a_journal_is_announced_only_once(self):
        self.loop._applied_steps = 1
        self.loop._write_journal("готово")
        self.loop._write_journal("готово ещё раз")
        self.assertEqual(self.paths, [("скачай кафе", 1)])
        self.assertEqual(self.emitted, ["/tmp/run_x.md"])

    def test_final_apply_counts_only_successes_and_writes_the_journal(self):
        calls = [
            ToolCall(id="ok", name="unknown_ok"),
            ToolCall(id="bad", name="unknown_bad"),
            ToolCall(id="skip", name="unknown_skip"),
        ]
        results = [
            ToolResult(call=calls[0], payload={"status": "done"}),
            ToolResult.failure(calls[1], "failed"),
            ToolResult(call=calls[2], ok=False, payload={"status": "skipped", "error": "not run"}),
        ]
        self.loop._batch = _FinalBatch(calls, results)
        self.loop._journal_outcome = "готово"
        saved_snapshot = batch_apply_module.take_snapshot
        batch_apply_module.take_snapshot = lambda: True
        try:
            self.loop.confirm_pending()
        finally:
            batch_apply_module.take_snapshot = saved_snapshot
        self.assertEqual(self.paths, [("скачай кафе", 1)])
        self.assertEqual(self.emitted, ["/tmp/run_x.md"])
        self.assertEqual(
            self.outcomes,
            ["Apply finished: 1 applied, 1 failed, 1 skipped."],
        )
        self.assertNotIn("готово", self.outcomes[0])

    def test_snapshot_failure_is_the_journal_outcome_not_model_text(self):
        call = ToolCall(id="blocked", name="unknown_write")
        self.loop._batch = _FinalBatch([call], [])
        self.loop._applied_steps = 1
        self.loop._journal_outcome = "готово"
        with (
            mock.patch.object(batch_apply_module, "take_snapshot", return_value=False),
            mock.patch.object(batch_apply_module, "snapshot_error", return_value="snapshot failed"),
        ):
            self.loop.confirm_pending()

        self.assertEqual(self.outcomes, ["snapshot failed"])
        self.assertNotIn("готово", self.outcomes[0])


class _FinalBatch:
    def __init__(self, calls, results):
        self._calls = calls
        self._results = results
        self.is_applying = False
        self.executing_tool = ""

    def __bool__(self):
        return bool(self._calls)

    def pending(self):
        return list(self._calls)

    def clear(self):
        self._calls = []

    def apply(self, on_start, on_finish, _expected_project_identity):
        self._calls = []
        for result in self._results:
            on_start(result.call)
            on_finish(result.call, result)
        return list(self._results)


if __name__ == "__main__":
    unittest.main()
