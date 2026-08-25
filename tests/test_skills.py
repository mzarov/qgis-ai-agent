import os
import pathlib
import unittest

from qgis_ai_agent.qgis_tools.registry import get_tools_for_skills
from qgis_ai_agent.skills.base import parse_skill_markdown
from qgis_ai_agent.skills.registry import SkillRegistry

SKILLS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "qgis_ai_agent", "skills",
)


class FrontmatterTest(unittest.TestCase):
    def test_name_description_and_tools(self):
        skill = parse_skill_markdown(
            "---\nname: demo\ndescription: Про демо.\ntools: [a, b]\n---\n\nТело.\n"
        )
        self.assertEqual(skill.name, "demo")
        self.assertEqual(skill.description, "Про демо.")
        self.assertEqual(skill.tool_names, ["a", "b"])
        self.assertEqual(skill.body, "Тело.")

    def test_quotes_are_stripped(self):
        skill = parse_skill_markdown("---\nname: 'demo'\ntools: ['a', \"b\"]\n---\n")
        self.assertEqual(skill.name, "demo")
        self.assertEqual(skill.tool_names, ["a", "b"])

    def test_missing_frontmatter_falls_back_to_folder(self):
        skill = parse_skill_markdown("Просто тело.", fallback_name="layout")
        self.assertEqual(skill.name, "layout")
        self.assertEqual(skill.body, "Просто тело.")

    def test_summary_line_shape(self):
        skill = parse_skill_markdown("---\nname: a\ndescription: b\n---\n")
        self.assertEqual(skill.summary_line(), "- a: b")


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = SkillRegistry(SKILLS_ROOT)

    def test_every_skill_on_disk_is_found(self):
        on_disk = sorted(path.parent.name for path in pathlib.Path(SKILLS_ROOT).rglob("SKILL.md"))
        self.assertTrue(on_disk, "в skills/ не найдено ни одного SKILL.md")
        self.assertEqual(self.registry.names(), on_disk)

    def test_every_skill_declares_description_and_body(self):
        for skill in self.registry.all_skills():
            self.assertTrue(skill.description, skill.name)
            self.assertTrue(skill.body, skill.name)

    def test_declared_tools_match_registry(self):
        for name in self.registry.names():
            declared = self.registry.get(name).tool_names
            actual = [tool.name for tool in get_tools_for_skills([name])]
            self.assertEqual(declared, actual, f"скилл {name}")

    def test_summaries_block_lists_all(self):
        block = self.registry.summaries_block()
        for name in self.registry.names():
            self.assertIn(name, block)

    def test_bodies_block_only_for_asked(self):
        block = self.registry.bodies_block(["processing"])
        self.assertIn("Geoprocessing", block)
        self.assertNotIn("Layer appearance", block)

    def test_unknown_skill_gives_nothing(self):
        self.assertIsNone(self.registry.get("нет-такого"))
        self.assertEqual(self.registry.bodies_block(["нет-такого"]), "")


if __name__ == "__main__":
    unittest.main()
