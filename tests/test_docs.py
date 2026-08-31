import pathlib
import re
import unittest

from ai_agent.qgis_tools.registry import ALL_TOOLS
from ai_agent.skills.registry import SKILL_REGISTRY

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
REPO_ROOT = DOCS.parent
RU_SUFFIX = ".ru.md"
HEADING = re.compile(r"^#{1,3} ", re.MULTILINE)


def english_pages() -> list[pathlib.Path]:
    return sorted(path for path in DOCS.glob("*.md") if not path.name.endswith(RU_SUFFIX))


def russian_pages() -> list[pathlib.Path]:
    return sorted(DOCS.glob(f"*{RU_SUFFIX}"))


class MirrorTest(unittest.TestCase):
    def test_every_english_page_has_a_russian_twin(self):
        orphans = [
            page.name for page in english_pages() if not page.with_name(page.name[: -len(".md")] + RU_SUFFIX).is_file()
        ]
        self.assertEqual(orphans, [])

    def test_every_russian_page_has_an_english_original(self):
        orphans = [
            page.name for page in russian_pages() if not page.with_name(page.name[: -len(RU_SUFFIX)] + ".md").is_file()
        ]
        self.assertEqual(orphans, [])

    def test_there_are_pages_at_all(self):
        self.assertGreaterEqual(len(english_pages()), 5)

    def test_twins_do_not_drift_apart_in_structure(self):
        for page in english_pages():
            twin = page.with_name(page.name[: -len(".md")] + RU_SUFFIX)
            original = len(HEADING.findall(page.read_text(encoding="utf-8")))
            mirrored = len(HEADING.findall(twin.read_text(encoding="utf-8")))
            self.assertEqual(mirrored, original, page.name)


class NavTest(unittest.TestCase):
    def test_the_nav_lists_only_existing_english_pages(self):
        config = (DOCS.parent / "mkdocs.yml").read_text(encoding="utf-8")
        listed = re.findall(r":\s*([\w.]+\.md)\s*$", config, re.MULTILINE)
        self.assertTrue(listed)
        for name in listed:
            self.assertTrue((DOCS / name).is_file(), name)

    def test_every_english_page_is_in_the_nav(self):
        config = (DOCS.parent / "mkdocs.yml").read_text(encoding="utf-8")
        missing = [page.name for page in english_pages() if page.name not in config]
        self.assertEqual(missing, [])


class PublishedClaimsTest(unittest.TestCase):
    def test_tool_and_skill_counts_match_the_registries(self):
        claims = {
            REPO_ROOT / "README.md": f"twelve domains, {len(ALL_TOOLS)} tools",
            DOCS / "index.md": f"Twelve domains, {len(ALL_TOOLS)} tools",
            DOCS / "index.ru.md": f"Двенадцать доменов, {len(ALL_TOOLS)} инструментов",
        }
        self.assertEqual(len(SKILL_REGISTRY.names()), 12)
        for path, phrase in claims.items():
            self.assertIn(phrase, path.read_text(encoding="utf-8"), path.name)

    def test_removed_tool_browser_is_not_advertised(self):
        published = [REPO_ROOT / "ai_agent" / "metadata.txt", *english_pages(), *russian_pages()]
        obsolete_claims = ("tool browser", "capability browser", "браузер инструментов", "браузер тулов")
        for path in published:
            text = path.read_text(encoding="utf-8").lower()
            for claim in obsolete_claims:
                self.assertNotIn(claim, text, path.name)

    def test_setup_names_the_qgis_authentication_database(self):
        english = (DOCS / "SETUP.md").read_text(encoding="utf-8").lower()
        russian = (DOCS / "SETUP.ru.md").read_text(encoding="utf-8").lower()
        self.assertIn("qgis authentication database", english)
        self.assertIn("базе учётных данных qgis", russian)

    def test_privacy_pages_name_real_values_and_images(self):
        for name, attribute_word in (("privacy.md", "attribute"), ("privacy.ru.md", "атрибут")):
            text = (DOCS / name).read_text(encoding="utf-8").lower()
            self.assertIn(attribute_word, text)
            self.assertIn("png", text)

    def test_privacy_pages_distinguish_agent_consent_from_connection_test(self):
        english = " ".join((DOCS / "privacy.md").read_text(encoding="utf-8").lower().split())
        russian = " ".join((DOCS / "privacy.ru.md").read_text(encoding="utf-8").lower().split())
        self.assertIn("first agent run", english)
        self.assertIn("test connection", english)
        self.assertIn("explicit exception", english)
        self.assertIn("первым запуском агента", russian)
        self.assertIn("проверить подключение", russian)
        self.assertIn("явное исключение", russian)

    def test_privacy_pages_disclose_the_plaintext_run_journal(self):
        english = " ".join((DOCS / "privacy.md").read_text(encoding="utf-8").lower().split())
        russian = " ".join((DOCS / "privacy.ru.md").read_text(encoding="utf-8").lower().split())
        self.assertIn("plaintext markdown", english)
        self.assertIn("ai_agent_runs", english)
        self.assertIn("not encrypted", english)
        self.assertIn("active qgis profile", english)
        self.assertIn("0700", english)
        self.assertIn("0600", english)
        self.assertIn("markdown", russian)
        self.assertIn("ai_agent_runs", russian)
        self.assertIn("не является шифрованием", russian)
        self.assertIn("активного профиля qgis", russian)
        self.assertIn("0700", russian)
        self.assertIn("0600", russian)


if __name__ == "__main__":
    unittest.main()
