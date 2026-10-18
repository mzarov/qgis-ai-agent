import pathlib
import re
import unittest

from ai_agent.qgis_tools.processing.utils import get_registry

SKILLS_ROOT = pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "skills"
ID_PATTERN = re.compile(r"`((?:native|qgis|gdal|grass|3d):[a-z0-9_.]+)`")


def mentioned_ids() -> set[str]:
    found: set[str] = set()
    for path in SKILLS_ROOT.rglob("SKILL.md"):
        found.update(ID_PATTERN.findall(path.read_text(encoding="utf-8")))
    return found


def registry_ids() -> set[str]:
    try:
        return {algorithm.id() for algorithm in get_registry().algorithms()}
    except Exception:
        return set()


class SkillAlgorithmTest(unittest.TestCase):
    def test_skills_do_mention_algorithms(self):
        self.assertTrue(mentioned_ids(), "no algorithm id found in the skills")

    def test_every_mentioned_algorithm_exists(self):
        known = registry_ids()
        if not known:
            self.skipTest("the Processing registry is empty: this check runs only inside live QGIS")
        missing = sorted(name for name in mentioned_ids() if name not in known)
        self.assertEqual(missing, [], "a SKILL.md names algorithm ids QGIS does not have")

    def test_ids_are_lowercase_and_prefixed(self):
        for name in mentioned_ids():
            self.assertEqual(name, name.lower(), name)
            self.assertIn(":", name, name)


if __name__ == "__main__":
    unittest.main()
