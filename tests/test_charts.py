import json
import tempfile
import unittest
from unittest import mock

from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.llm.turns import ToolCall
from ai_agent.core.state.conversation import VISUAL_ROLE, ConversationState
from ai_agent.core.state.store import SessionStore
from ai_agent.qgis_tools.base import RESULT_VISUAL_KEY
from ai_agent.qgis_tools.charts import chart_layer, spec
from ai_agent.qgis_tools.charts.show_chart import ShowChartTool
from ai_agent.ui import chart_scale


class SpecTest(unittest.TestCase):
    def test_a_valid_chart_is_cleaned(self):
        drawn = spec.chart(
            "bar", "  Population  ", ["A", "B"], [{"name": "2020", "values": ["3", None]}], unit="people"
        )
        self.assertEqual(drawn["title"], "Population")
        self.assertEqual(drawn["series"][0]["values"], [3.0, None])

    def test_mistakes_come_back_with_the_fix(self):
        with self.assertRaisesRegex(ValueError, "2 values for 3 labels"):
            spec.chart("bar", "t", ["a", "b", "c"], [{"name": "s", "values": [1, 2]}])
        with self.assertRaisesRegex(ValueError, "too many"):
            spec.chart("line", "t", ["a"], [{"name": str(n), "values": [1]} for n in range(5)])
        with self.assertRaisesRegex(ValueError, "not a number"):
            spec.chart("bar", "t", ["a"], [{"name": "s", "values": ["many"]}])
        with self.assertRaisesRegex(ValueError, "negative"):
            spec.chart("pie", "t", ["a", "b"], [{"name": "s", "values": [1, -1]}])
        with self.assertRaisesRegex(ValueError, "kind"):
            spec.chart("radar", "t", ["a"], [{"name": "s", "values": [1]}])

    def test_a_pie_keeps_the_largest_slices_and_folds_the_rest(self):
        labels = [chr(65 + n) for n in range(10)]
        drawn = spec.chart("pie", "t", labels, [{"name": "s", "values": list(range(1, 11))}])
        self.assertEqual(len(drawn["labels"]), spec.MAX_PIE_SLICES)
        self.assertEqual(drawn["labels"][-1], spec.OTHER)
        self.assertEqual(drawn["series"][0]["values"][-1], 1 + 2 + 3)

    def test_a_scatter_pairs_x_with_values(self):
        drawn = spec.chart("scatter", "t", [], [{"name": "s", "x": [1, 2], "values": [3, 4]}])
        self.assertEqual(drawn["series"][0]["x"], [1.0, 2.0])
        with self.assertRaisesRegex(ValueError, "as many x"):
            spec.chart("scatter", "t", [], [{"name": "s", "x": [1], "values": [3, 4]}])

    def test_a_table_clips_rows_columns_and_cells(self):
        drawn = spec.table("t", [f"c{n}" for n in range(12)], [[1.5, None, "x" * 300]] * 60, 99)
        self.assertEqual((len(drawn["columns"]), len(drawn["rows"])), (spec.MAX_TABLE_COLUMNS, spec.MAX_TABLE_ROWS))
        self.assertEqual(drawn["rows"][0][:2], ["1.5", ""])
        self.assertEqual(len(drawn["rows"][0][2]), spec.MAX_CELL)


class ChartLayerMathTest(unittest.TestCase):
    def setUp(self):
        self.layer = mock.Mock()
        self.layer.name.return_value = "districts"

    def test_a_histogram_bins_the_numbers(self):
        rows = [(value, None) for value in (0, 1, 2, 3, 4, 10)]
        drawn = chart_layer._histogram(rows, {"value": "pop", "bins": 2}, self.layer)
        self.assertEqual(drawn["kind"], "histogram")
        self.assertEqual(drawn["series"][0]["values"], [5.0, 1.0])

    def test_groups_sum_count_and_fold_the_tail(self):
        rows = [(10, "a"), (5, "a"), (1, "b"), (2, None), (7, "c")]
        summed = chart_layer._grouped(rows, {"value": "pop", "top": 2}, "sum", "auto", self.layer)
        self.assertEqual(summed["labels"], ["a", spec.OTHER])
        self.assertEqual(summed["series"][0]["values"], [15.0, 10.0])
        counted = chart_layer._grouped(rows, {}, "count", "pie", self.layer)
        self.assertEqual(counted["kind"], "pie")
        self.assertIn(chart_layer.EMPTY, counted["labels"])
        means = chart_layer._grouped(rows, {"value": "pop", "top": 1}, "mean", "auto", self.layer)
        self.assertEqual((means["labels"], means["series"][0]["values"]), (["a"], [7.5]))


class ScaleTest(unittest.TestCase):
    def test_ticks_are_round_and_cover_the_data(self):
        self.assertEqual(chart_scale.nice_ticks(0, 95000), [0, 25000, 50000, 75000, 100000])
        ticks = chart_scale.nice_ticks(-3, 7)
        self.assertLessEqual(ticks[0], -3)
        self.assertGreaterEqual(ticks[-1], 7)
        flat = chart_scale.nice_ticks(5, 5)
        self.assertTrue(flat[0] <= 5 < flat[-1])

    def test_numbers_and_layouts(self):
        self.assertEqual(chart_scale.compact(1_234_567), "1.23M")
        self.assertEqual(chart_scale.compact(950), "950")
        self.assertEqual(chart_scale.compact(0.0123), "0.0123")
        self.assertTrue(chart_scale.horizontal_bars(["Central district"], 1))
        self.assertFalse(chart_scale.horizontal_bars(["A", "B"], 1))
        self.assertEqual(chart_scale.thinned(20, 100, 25), 5)


class PlumbingTest(unittest.TestCase):
    def test_the_executor_hands_the_chart_to_the_feed_and_not_to_the_model(self):
        call = ToolCall(
            id="1",
            name="show_chart",
            arguments={"kind": "bar", "title": "T", "labels": ["a"], "series": [{"name": "s", "values": [1]}]},
        )
        result = ToolExecutor().run(call)
        self.assertTrue(result.ok)
        self.assertNotIn(RESULT_VISUAL_KEY, result.payload)
        self.assertEqual(result.visual["type"], "chart")
        self.assertNotIn("visual", result.to_text())

    def test_a_failed_tool_shows_nothing(self):
        result = ToolExecutor().run(ToolCall(id="1", name="show_chart", arguments={"kind": "bar", "series": []}))
        self.assertFalse(result.ok)
        self.assertIsNone(result.visual)

    def test_a_saved_chart_replays_but_never_reaches_the_model(self):
        store = SessionStore(tempfile.mkdtemp())
        conversation = ConversationState(store)
        conversation.add("user", "chart it")
        drawn = ShowChartTool().execute(
            {"kind": "bar", "title": "T", "labels": ["a"], "series": [{"name": "s", "values": [2]}]}
        )
        conversation.add_visual(drawn[RESULT_VISUAL_KEY])
        conversation.add("assistant", "Here it is.")
        self.assertEqual([message["role"] for message in conversation.window()], ["user", "assistant"])
        replayed = conversation.replayable()
        self.assertEqual(replayed[1]["role"], VISUAL_ROLE)
        self.assertEqual(replayed[1]["visual"]["title"], "T")
        conversation.messages.append({"role": VISUAL_ROLE, "content": "{broken"})
        self.assertEqual(len(conversation.replayable()), 3)
        self.assertEqual(json.loads(conversation.messages[1]["content"])["kind"], "bar")


if __name__ == "__main__":
    unittest.main()
