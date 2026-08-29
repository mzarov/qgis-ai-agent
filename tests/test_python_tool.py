import pathlib
import unittest

from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from qgis_ai_agent.qgis_tools.python.run_python import MAX_CODE_CHARS, RunPythonTool, _checked_code
from qgis_ai_agent.qgis_tools.python.sandbox import BudgetExceeded, LineBudget, run_snippet
from qgis_ai_agent.ui.dock_widget import _destructive_confirmation_text

DOCK_SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "qgis_ai_agent" / "ui" / "dock_widget.py").read_text(
    encoding="utf-8"
)


class CheckedCodeTest(unittest.TestCase):
    def test_empty_code_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            _checked_code("   ")
        self.assertIn("nothing to run", str(caught.exception))

    def test_syntax_error_is_caught_before_running(self):
        with self.assertRaises(ValueError) as caught:
            _checked_code("def broken(:")
        self.assertIn("does not parse", str(caught.exception))

    def test_oversized_snippet_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            _checked_code("x = 1\n" * MAX_CODE_CHARS)
        self.assertIn("read", str(caught.exception))

    def test_valid_code_passes_through(self):
        self.assertEqual(_checked_code(" print(1) "), "print(1)")


class BudgetTest(unittest.TestCase):
    def test_a_loop_is_stopped_by_the_budget(self):
        result = run_snippet("while True:\n    pass\n", limit=500)
        self.assertIn("best-effort budget", result["error"])
        self.assertIn("not a security sandbox", result["error"])
        self.assertGreaterEqual(result["lines_executed"], 500)

    def test_the_budget_restores_the_previous_tracer(self):
        import sys

        marker = sys.gettrace()
        with LineBudget(10):
            pass
        self.assertIs(sys.gettrace(), marker)

    def test_budget_raises_only_past_the_limit(self):
        budget = LineBudget(2)
        budget.used = 1
        with self.assertRaises(BudgetExceeded):
            for _ in range(5):
                budget._trace(None, "line", None)


class RunSnippetTest(unittest.TestCase):
    def test_printed_output_comes_back(self):
        result = run_snippet("print('hello from qgis')")
        self.assertIn("hello from qgis", result["output"])
        self.assertNotIn("error", result)

    def test_silence_is_flagged_as_a_note(self):
        result = run_snippet("x = 2 + 2")
        self.assertIn("print()", result["output_note"])

    def test_runtime_error_returns_message_and_traceback(self):
        result = run_snippet("raise ValueError('boom')")
        self.assertIn("boom", result["error"])
        self.assertIn("ValueError", result["traceback"])

    def test_exception_with_an_empty_message_is_still_a_failure(self):
        result = run_snippet("raise RuntimeError()")
        self.assertEqual(result["error"], "RuntimeError")

    def test_long_output_is_truncated(self):
        result = run_snippet("print('x' * 20000)")
        self.assertLess(len(result["output"]), 20000)
        self.assertIn("truncated", result["output"])

    def test_prepared_names_are_available(self):
        result = run_snippet("print(project is not None)")
        self.assertIn("True", result["output"])

    def test_a_failure_still_reports_what_was_printed(self):
        result = run_snippet("print('before')\nraise RuntimeError('after')")
        self.assertIn("before", result["output"])
        self.assertIn("after", result["error"])


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = RunPythonTool()

    def test_the_tool_is_destructive_so_the_user_reads_the_code(self):
        self.assertEqual(self.tool.safety, SAFETY_DESTRUCTIVE)

    def test_intent_is_mandatory(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"code": "print(1)"})
        self.assertIn("intent", str(caught.exception))

    def test_prepare_accepts_a_documented_snippet(self):
        prepared = self.tool.prepare({"code": "print(1)", "intent": "check something"})
        self.assertEqual(prepared["code"], "print(1)")

    def test_summary_shows_the_intent_and_never_raises(self):
        self.assertIn("check the CRS", self.tool.summarize_call({"intent": "check the CRS"}))
        self.assertTrue(self.tool.summarize_call({}).strip())

    def test_summary_falls_back_to_the_code_when_intent_is_missing(self):
        self.assertIn("print", self.tool.summarize_call({"code": "print(1)"}))

    def test_execute_returns_the_intent_with_the_output(self):
        result = self.tool.execute({"code": "print('ok')", "intent": "smoke"})
        self.assertEqual(result["intent"], "smoke")
        self.assertIn("ok", result["output"])

    def test_description_does_not_promise_a_security_sandbox(self):
        self.assertIn("not a security sandbox", self.tool.build_description())

    def test_runtime_error_is_a_failed_tool_result_with_context(self):
        result = ToolExecutor().run(
            ToolCall(
                id="python_1",
                name="run_python",
                arguments={"code": "print('before')\nraise RuntimeError('boom')", "intent": "test failure"},
            )
        )
        self.assertFalse(result.ok)
        self.assertIn("before", result.payload["output"])
        self.assertIn("boom", result.payload["error"])

    def test_exact_code_is_in_the_always_visible_confirmation_text(self):
        code = "print('<exact>')\nproject.clear()"
        text = _destructive_confirmation_text(["Running Python: smoke"], code)
        self.assertIn("Exact code to be executed", text)
        self.assertIn(code, text)

    def test_code_confirmation_uses_a_permanently_visible_fixed_font_editor(self):
        body = DOCK_SOURCE.split("def _confirm_code(")[1].split("\ndef ")[0]
        self.assertIn("QPlainTextEdit", body)
        self.assertIn("setReadOnly(True)", body)
        self.assertIn("SystemFont.FixedFont", body)
        self.assertIn("setMinimumHeight", body)


if __name__ == "__main__":
    unittest.main()
