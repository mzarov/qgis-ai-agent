import unittest

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.core.agent import prompts
from ai_agent.core.orchestrator import slash
from ai_agent.skills.registry import SKILL_REGISTRY
from ai_agent.ui.composer import Composer, slash_query
from ai_agent.ui.skill_popup import MAX_ROWS, SkillPopup, match_skills

ITEMS = [
    ("osm", "Download OpenStreetMap data", "builtin"),
    ("style", "Style layers", "builtin"),
    ("cafes", "House cafe rules", "local"),
    ("processing", "Run algorithms", "builtin"),
]


class ParseSlashTest(unittest.TestCase):
    def test_command_and_rest_are_split(self):
        self.assertEqual(slash.parse_slash("/osm скачай кафе"), ("osm", "скачай кафе"))

    def test_command_is_case_insensitive_and_trimmed(self):
        self.assertEqual(slash.parse_slash("  /OSM  "), ("osm", ""))

    def test_a_slash_in_the_middle_is_plain_text(self):
        self.assertEqual(slash.parse_slash("hello /osm"), ("", "hello /osm"))

    def test_empty_and_lone_slash_are_not_commands(self):
        self.assertEqual(slash.parse_slash(""), ("", ""))
        self.assertEqual(slash.parse_slash("/"), ("", ""))

    def test_newline_also_ends_the_command(self):
        self.assertEqual(slash.parse_slash("/osm\nкафе"), ("osm", "кафе"))

    def test_default_prompt_names_the_skill(self):
        self.assertIn("'osm'", slash.prompt_for("osm", ""))
        self.assertEqual(slash.prompt_for("osm", "text"), "text")

    def test_known_skills_are_recognised(self):
        self.assertTrue(slash.is_known_skill("osm"))
        self.assertFalse(slash.is_known_skill("nope"))

    def test_available_names_are_listed_as_commands(self):
        self.assertIn("/osm", slash.available_names())
        self.assertIn("/inspect", slash.available_names())


class PromptTest(unittest.TestCase):
    def test_invoked_skills_are_named_in_the_system_prompt(self):
        prompt = prompts.build_system_prompt("", ["inspect", "osm"], invoked_skills=["osm"])
        self.assertIn(prompts.INVOKED_SKILLS_HEADER + "osm.", prompt)
        self.assertIn("# Skill: osm", prompt)

    def test_without_invoked_skills_the_header_is_absent(self):
        prompt = prompts.build_system_prompt("", ["inspect"])
        self.assertNotIn(prompts.INVOKED_SKILLS_HEADER, prompt)

    def test_the_core_prompt_asks_for_one_turn_skill_loading(self):
        self.assertIn("load every skill it needs in one turn", prompts.CORE_PROMPT)

    def test_load_skill_enum_covers_every_registered_skill(self):
        schema = prompts.build_load_skill_schema(SKILL_REGISTRY.names())
        self.assertEqual(schema["function"]["parameters"]["properties"]["name"]["enum"], SKILL_REGISTRY.names())


class SlashQueryTest(unittest.TestCase):
    def test_query_is_the_text_after_the_slash(self):
        self.assertEqual(slash_query("/os"), "os")
        self.assertEqual(slash_query("/"), "")

    def test_a_space_closes_the_query(self):
        self.assertIsNone(slash_query("/osm text"))
        self.assertIsNone(slash_query("/osm "))

    def test_plain_text_has_no_query(self):
        self.assertIsNone(slash_query("hello"))
        self.assertIsNone(slash_query(""))


class MatchTest(unittest.TestCase):
    def test_prefix_matches_come_before_substring_matches(self):
        names = [name for name, _, _ in match_skills("s", ITEMS)]
        self.assertEqual(names, ["style", "osm", "cafes", "processing"])

    def test_empty_query_lists_everything_in_order(self):
        self.assertEqual(match_skills("", ITEMS), ITEMS)

    def test_no_match_is_empty(self):
        self.assertEqual(match_skills("zzz", ITEMS), [])

    def test_the_list_is_capped(self):
        many = [(f"skill{index:02d}", "d", "builtin") for index in range(20)]
        self.assertEqual(len(match_skills("skill", many)), MAX_ROWS)


class PopupTest(unittest.TestCase):
    def setUp(self):
        self.host = QWidget()
        self.popup = SkillPopup(self.host)

    def test_selection_starts_at_the_best_match_and_cycles(self):
        self.popup.show_matches("s", ITEMS, QWidget())
        self.assertEqual(self.popup.current_name(), "style")
        self.popup.move_selection(1)
        self.assertEqual(self.popup.current_name(), "osm")
        self.popup.move_selection(-2)
        self.assertEqual(self.popup.current_name(), "processing")

    def test_choosing_emits_the_name(self):
        chosen = []
        self.popup.chosen.connect(chosen.append)
        self.popup.show_matches("ca", ITEMS, QWidget())
        self.assertTrue(self.popup.choose_current())
        self.assertEqual(chosen, ["cafes"])

    def test_nothing_to_choose_when_nothing_matches(self):
        self.popup.show_matches("zzz", ITEMS, QWidget())
        self.assertEqual(self.popup.current_name(), "")
        self.assertFalse(self.popup.choose_current())


class ComposerWiringTest(unittest.TestCase):
    def test_the_composer_accepts_a_skill_source_and_a_host(self):
        composer = Composer()
        composer.set_skill_source(lambda: ITEMS)
        composer.set_popup_host(QWidget())
        self.assertIsNotNone(composer._popup)

    def test_inserting_a_skill_leaves_a_trailing_space_for_the_request(self):
        composer = Composer()
        composer.set_popup_host(QWidget())
        seen = []
        composer._edit.setPlainText = seen.append
        composer._insert_skill("osm")
        self.assertEqual(seen, ["/osm "])


if __name__ == "__main__":
    unittest.main()
