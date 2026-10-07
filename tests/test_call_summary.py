import unittest

from ai_agent.qgis_tools.call_summary import CallSummary
from ai_agent.qgis_tools.registry import summarize_tool_call
from ai_agent.ui.activity import StepRow, step_markup
from ai_agent.ui.conversation import ConversationView


def marked(summary: CallSummary) -> list[str]:
    return [span for span, is_value in summary.parts if is_value]


class MarkingTest(unittest.TestCase):
    def test_argument_values_are_marked_and_the_text_is_unchanged(self):
        text = "Graduating 'districts' by 'population', classes: 5."
        summary = CallSummary.marking(text, {"layer_name": "districts", "field": "population", "classes": 5})
        self.assertEqual(summary, text)
        self.assertEqual(marked(summary), ["districts", "population", "5"])

    def test_a_value_inside_a_longer_word_stays_unmarked(self):
        summary = CallSummary.marking("Renamed field 'name'", {"field": "name"})
        self.assertEqual(marked(summary), ["name"])
        self.assertEqual(summary.parts[0], ("Renamed field '", False))

    def test_the_longest_value_wins_an_overlap(self):
        summary = CallSummary.marking("Reading 'Main rivers'", {"a": "Main", "b": "Main rivers"})
        self.assertEqual(marked(summary), ["Main rivers"])

    def test_nested_values_count_and_flags_and_one_letter_strings_do_not(self):
        summary = CallSummary.marking("Buffer x INPUT=roads", {"parameters": {"INPUT": "roads"}, "x": "x", "f": True})
        self.assertEqual(marked(summary), ["roads"])

    def test_filling_a_template_keeps_the_marks_of_a_summary_inside(self):
        inner = CallSummary.marking("Reading 'roads'", {"layer_name": "roads"})
        summary = CallSummary.of("Rejected: {0}", inner)
        self.assertEqual(summary, "Rejected: Reading 'roads'")
        self.assertEqual(marked(summary), ["roads"])
        self.assertEqual(marked(CallSummary.of("Loading knowledge: {0}", "style")), ["style"])


class RegistryTest(unittest.TestCase):
    def test_every_call_label_comes_back_marked(self):
        summary = summarize_tool_call("describe_layer", {"layer_name": "districts"})
        self.assertIsInstance(summary, CallSummary)
        self.assertEqual(marked(summary), ["districts"])

    def test_an_unknown_tool_still_gets_a_label(self):
        self.assertIsInstance(summarize_tool_call("no_such_tool", {}), CallSummary)


class StepMarkupTest(unittest.TestCase):
    palette = ConversationView().palette()

    def test_values_are_escaped_and_lose_their_quotes(self):
        summary = CallSummary.marking("Reading layer '<b>x</b>'", {"layer_name": "<b>x</b>"})
        markup = step_markup(summary, self.palette)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;</span>", markup)
        self.assertNotIn("'", markup)
        self.assertNotIn("<b>", markup)

    def test_a_row_drops_the_closing_full_stop(self):
        summary = CallSummary.marking("Reading layer 'roads'.", {"layer_name": "roads"})
        self.assertFalse(step_markup(summary, self.palette).endswith(".</span>"))
        self.assertNotIn("project.<", StepRow("Reading the project.", self.palette)._label.text())

    def test_a_label_without_values_is_all_wording(self):
        markup = step_markup("Reading the project layers.", self.palette)
        self.assertIn("Reading the project layers</span>", markup)
        self.assertNotIn("font-weight", markup)

    def test_a_skill_being_loaded_wears_the_skill_tag(self):
        summary = CallSummary.marking("Using style.", {})
        summary.skill = "knowledge"
        self.assertIn("skill", step_markup(summary, self.palette))


if __name__ == "__main__":
    unittest.main()
