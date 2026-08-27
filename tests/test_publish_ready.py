import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "qgis_ai_agent"
METADATA = PACKAGE / "metadata.txt"
REQUIRED_FIELDS = ("name", "qgisMinimumVersion", "description", "about", "version", "author", "email", "repository")
VALID_CATEGORIES = ("Raster", "Vector", "Database", "Mesh", "Web")
MANDATORY_IN_ZIP = ("metadata.txt", "__init__.py", "LICENSE")
CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def metadata_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in METADATA.read_text(encoding="utf-8").split("\n"):
        if "=" in line and not line.startswith((" ", "\t")):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


class MetadataRulesTest(unittest.TestCase):
    def setUp(self):
        self.values = metadata_values()

    def test_required_fields_present(self):
        missing = [name for name in REQUIRED_FIELDS if not self.values.get(name)]
        self.assertEqual(missing, [])

    def test_category_is_valid_or_absent(self):
        category = self.values.get("category")
        if category:
            self.assertIn(category, VALID_CATEGORIES)

    def test_links_point_at_a_repository_not_an_archive(self):
        for field in ("repository", "homepage", "tracker"):
            url = self.values.get(field, "")
            if url:
                self.assertTrue(url.startswith("https://"), field)
                self.assertFalse(url.endswith(".zip"), field)

    def test_reviewers_can_read_the_english_summary(self):
        for field in ("description", "about"):
            self.assertFalse(CYRILLIC.search(self.values.get(field, "")), field)

    def test_tags_are_english_and_lowercase(self):
        tags = [tag.strip() for tag in self.values.get("tags", "").split(",") if tag.strip()]
        self.assertTrue(tags)
        for tag in tags:
            self.assertFalse(CYRILLIC.search(tag), tag)
            self.assertEqual(tag, tag.lower(), tag)

    def test_third_party_service_is_disclosed(self):
        about = self.values.get("about", "").lower()
        self.assertIn("api key", about)

    def test_name_does_not_repeat_the_word_plugin(self):
        self.assertNotIn("plugin", self.values.get("name", "").lower())


class LicenceTest(unittest.TestCase):
    def test_licence_file_has_no_extension(self):
        self.assertTrue((REPO_ROOT / "LICENSE").is_file())
        self.assertFalse((REPO_ROOT / "LICENSE.txt").exists())

    def test_licence_is_gpl(self):
        self.assertIn("GNU GENERAL PUBLIC LICENSE", (REPO_ROOT / "LICENSE").read_text())


class ScannerConfigTest(unittest.TestCase):
    def test_bandit_config_travels_inside_the_package(self):
        config = PACKAGE / ".bandit"
        self.assertTrue(config.is_file())
        self.assertIn("[bandit]", config.read_text())

    def test_only_deliberate_patterns_are_skipped(self):
        skips = (PACKAGE / ".bandit").read_text().split("skips")[1]
        self.assertNotIn("B324", skips)
        self.assertNotIn("B303", skips)

    def test_weak_hash_was_fixed_not_silenced(self):
        settings = (PACKAGE / "core" / "settings.py").read_text()
        self.assertIn("usedforsecurity=False", settings)


class NetworkStackTest(unittest.TestCase):
    def test_no_module_imports_requests(self):
        offenders = [
            str(path.relative_to(PACKAGE))
            for path in PACKAGE.rglob("*.py")
            if "import requests" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_outgoing_calls_use_the_qgis_stack(self):
        users = [
            path for path in PACKAGE.rglob("*.py") if "QgsBlockingNetworkRequest" in path.read_text(encoding="utf-8")
        ]
        self.assertGreaterEqual(len(users), 2)


if __name__ == "__main__":
    unittest.main()
