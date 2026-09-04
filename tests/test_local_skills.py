import os
import pathlib
import tempfile
import unittest

from ai_agent.core import local_skills
from ai_agent.core.agent.skills import extend_loaded, skills_to_load, tools_for_skills
from ai_agent.skills.registry import LOCAL, SKILL_REGISTRY, SkillRegistry

BUILTIN_ROOT = str(pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "skills")
CAFES = """---
name: cafes
description: Find and style cafes the house way.
tools: [download_osm, list_layers]
---

# Cafes

Always download with amenity=cafe.
"""


def write_skill(root: str, folder: str, text: str) -> None:
    os.makedirs(os.path.join(root, folder), exist_ok=True)
    with open(os.path.join(root, folder, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write(text)


class LocalRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = SkillRegistry(BUILTIN_ROOT)
        write_skill(self.tmp.name, "cafes", CAFES)

    def tearDown(self):
        self.tmp.cleanup()

    def test_local_skill_is_discovered_with_local_origin(self):
        problems = self.registry.set_local_root(self.tmp.name)
        skill = self.registry.get("cafes")
        self.assertEqual(problems, [])
        self.assertEqual(skill.origin, LOCAL)
        self.assertIn("cafes", self.registry.names())
        self.assertEqual(self.registry.local_names(), ["cafes"])

    def test_builtin_skills_keep_their_origin(self):
        self.registry.set_local_root(self.tmp.name)
        self.assertEqual(self.registry.get("osm").origin, "builtin")

    def test_a_builtin_name_wins_on_collision(self):
        write_skill(self.tmp.name, "my-osm", CAFES.replace("name: cafes", "name: osm"))
        problems = self.registry.set_local_root(self.tmp.name)
        self.assertEqual(self.registry.get("osm").origin, "builtin")
        self.assertTrue(any("taken by a built-in" in problem for problem in problems))

    def test_missing_name_and_description_are_reported(self):
        write_skill(self.tmp.name, "nameless", "---\ndescription: x\n---\nbody")
        write_skill(self.tmp.name, "mute", "---\nname: mute\n---\nbody")
        problems = self.registry.set_local_root(self.tmp.name)
        self.assertTrue(any("nameless" in problem and "no name" in problem for problem in problems))
        self.assertTrue(any("mute" in problem and "no description" in problem for problem in problems))
        self.assertEqual(self.registry.local_names(), ["cafes"])

    def test_a_shouting_name_is_reported(self):
        write_skill(self.tmp.name, "loud", CAFES.replace("name: cafes", "name: My Skill"))
        problems = self.registry.set_local_root(self.tmp.name)
        self.assertTrue(any("My Skill" in problem for problem in problems))

    def test_refresh_picks_up_a_folder_added_later(self):
        self.registry.set_local_root(self.tmp.name)
        write_skill(self.tmp.name, "roads", CAFES.replace("name: cafes", "name: roads"))
        self.assertNotIn("roads", self.registry.local_names())
        self.registry.refresh_local()
        self.assertIn("roads", self.registry.local_names())

    def test_summaries_and_bodies_include_local_skills(self):
        self.registry.set_local_root(self.tmp.name)
        self.assertIn("- cafes: Find and style cafes", self.registry.summaries_block())
        self.assertIn("amenity=cafe", self.registry.bodies_block(["cafes"]))

    def test_clearing_the_root_forgets_local_skills(self):
        self.registry.set_local_root(self.tmp.name)
        self.registry.set_local_root(None)
        self.assertIsNone(self.registry.get("cafes"))


class LocalSkillsHelpersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_dir = local_skills.local_skills_dir
        local_skills.local_skills_dir = lambda: self.tmp.name
        write_skill(self.tmp.name, "cafes", CAFES.replace("list_layers", "list_layers, no_such_tool"))

    def tearDown(self):
        local_skills.local_skills_dir = self.saved_dir
        SKILL_REGISTRY.set_local_root(None)
        self.tmp.cleanup()

    def test_unknown_tools_are_dropped_and_reported(self):
        problems = local_skills.register_local_skills()
        self.assertEqual(SKILL_REGISTRY.get("cafes").tool_names, ["download_osm", "list_layers"])
        self.assertTrue(any("no_such_tool" in problem for problem in problems))

    def test_tools_of_a_local_skill_are_its_named_tools(self):
        local_skills.register_local_skills()
        self.assertEqual({tool.name for tool in tools_for_skills(["cafes"])}, {"download_osm", "list_layers"})

    def test_builtin_skill_tools_match_its_declared_list(self):
        local_skills.register_local_skills()
        self.assertEqual([tool.name for tool in tools_for_skills(["osm"])], SKILL_REGISTRY.get("osm").tool_names)

    def test_loading_a_local_skill_brings_the_domains_of_its_tools(self):
        local_skills.register_local_skills()
        names = skills_to_load("cafes")
        self.assertEqual(names[0], "cafes")
        self.assertEqual(sorted(names[1:]), ["inspect", "osm"])
        loaded = ["inspect"]
        extend_loaded(loaded, "cafes")
        self.assertEqual(loaded, ["inspect", "cafes", "osm"])

    def test_unknown_skill_loads_nothing(self):
        self.assertEqual(skills_to_load("nope"), [])

    def test_describe_lists_skills_and_problems(self):
        described = local_skills.describe_local_skills()
        self.assertEqual(described["path"], self.tmp.name)
        self.assertEqual(described["skills"][0]["name"], "cafes")
        self.assertEqual(described["skills"][0]["tools"], ["download_osm", "list_layers"])
        self.assertTrue(described["problems"])

    def test_the_example_is_written_once_and_is_a_valid_skill(self):
        path = local_skills.write_example_skill()
        self.assertTrue(os.path.isfile(path))
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\nkeep me\n")
        local_skills.write_example_skill()
        with open(path, encoding="utf-8") as handle:
            self.assertIn("keep me", handle.read())
        problems = local_skills.register_local_skills()
        self.assertIn("example-skill", SKILL_REGISTRY.local_names())
        self.assertFalse(any("example-skill" in problem for problem in problems))

    def test_choices_carry_origin_for_the_popup(self):
        choices = local_skills.skill_choices()
        origins = {name: origin for name, _, origin in choices}
        self.assertEqual(origins["cafes"], "local")
        self.assertEqual(origins["osm"], "builtin")

    def test_without_a_profile_directory_nothing_breaks(self):
        local_skills.local_skills_dir = lambda: ""
        self.assertEqual(local_skills.register_local_skills(), [])
        self.assertEqual(local_skills.write_example_skill(), "")
        self.assertEqual(local_skills.describe_local_skills()["skills"], [])


if __name__ == "__main__":
    unittest.main()
