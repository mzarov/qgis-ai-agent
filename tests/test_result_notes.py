import unittest

from ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call, summarize_tool_result


def note(tool: str, payload: dict) -> str:
    return summarize_tool_result(tool, {}, payload)


class ResultNoteTest(unittest.TestCase):
    """The line under a finished call says what it found, in a few words, from the payload alone."""

    def test_counts(self):
        self.assertEqual(note("list_layers", {"layers": [], "count": 3}), "3 layers")
        self.assertEqual(note("describe_layer", {"feature_count": 1}), "1 feature")
        self.assertEqual(note("describe_layer", {"feature_count_note": "not counted"}), "")
        self.assertEqual(note("query_layer", {"matched": 12}), "12 features matched")
        self.assertEqual(note("get_field_values", {"unique_values": ["a", "b"]}), "2 values")
        self.assertEqual(note("get_selection", {"selected_total": 0}), "0 features selected")
        self.assertEqual(note("select_features", {"selected": 8}), "8 features selected")
        self.assertEqual(note("search_web", {"results": [{}, {}]}), "2 results")
        self.assertEqual(note("search_processing", {"total_matched": 4}), "4 algorithms")

    def test_an_aggregate_shows_its_value(self):
        self.assertEqual(note("query_layer", {"aggregate": "sum", "value": 42.5, "matched": 3}), "sum: 42.5")
        self.assertEqual(note("query_layer", {"aggregate": "count", "groups": [{}, {}], "matched": 9}), "2 groups")

    def test_places_and_datasets_are_named(self):
        one = {"matches": [{"name": "Rotterdam, Zuid-Holland, Nederland"}]}
        self.assertEqual(note("geocode", one), "Rotterdam, Zuid-Holland, Nederland")
        self.assertEqual(note("geocode", {"matches": [{"name": "Paris"}, {"name": "Paris, TX"}]}), "Paris +1")
        self.assertEqual(note("geocode", {"matches": []}), "Nothing found")
        datasets = {"datasets": [{"title": title} for title in ("A", "B", "C", "D")]}
        self.assertEqual(note("find_open_data", datasets), "A, B, C +1")

    def test_scenes_name_the_best_one(self):
        scenes = {"scenes": [{"id": "x", "date": "2026-09-10", "cloud_cover": 2.1}, {"id": "y"}]}
        self.assertEqual(note("search_imagery", scenes), "2 scenes · best 2026-09-10, 2.1% cloud")
        self.assertEqual(note("search_imagery", {"scenes": []}), "No scenes")

    def test_a_tool_without_a_note_and_a_broken_payload_say_nothing(self):
        self.assertEqual(note("render_map", {"image_attached": True}), "")
        self.assertEqual(note("list_layers", {"count": "many"}), "")
        self.assertEqual(note("no_such_tool", {}), "")

    def test_a_call_summary_carries_its_skill(self):
        self.assertEqual(summarize_tool_call("list_layers", {}).skill, "inspect")
        self.assertEqual(
            summarize_tool_call("geocode", {"place": "Rotterdam"}).skill, get_tool_by_name("geocode").skill
        )


if __name__ == "__main__":
    unittest.main()
