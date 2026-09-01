import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "ai_agent"
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

    def test_actual_model_data_is_disclosed(self):
        about = self.values.get("about", "").lower()
        for phrase in (
            "feature attribute values",
            "exact map and layer extents",
            "layer filters and sources",
            "processing and python results",
            "rendered map or layout images",
            "plain json",
        ):
            self.assertIn(phrase, about)
        self.assertIn("off by default", about)
        self.assertNotIn("per-endpoint consent", about)

    def test_credential_storage_is_disclosed_without_promising_dependencies(self):
        about = self.values.get("about", "").lower()
        self.assertIn("qgis authentication database", about)
        self.assertNotIn("keyring", about)
        self.assertNotIn("external python dependency", about)

    def test_name_does_not_repeat_the_word_plugin(self):
        self.assertNotIn("plugin", self.values.get("name", "").lower())


class LicenceTest(unittest.TestCase):
    def test_licence_file_has_no_extension(self):
        self.assertTrue((REPO_ROOT / "LICENSE").is_file())
        self.assertFalse((REPO_ROOT / "LICENSE.txt").exists())

    def test_licence_is_gpl(self):
        self.assertIn("GNU GENERAL PUBLIC LICENSE", (REPO_ROOT / "LICENSE").read_text())

    def test_readme_badge_matches_the_gpl_v3_licence(self):
        self.assertIn("License: GPL-3.0", (REPO_ROOT / "README.md").read_text())


class ScannerConfigTest(unittest.TestCase):
    def test_scanners_run_with_stock_rules_no_config_anywhere(self):
        self.assertFalse((PACKAGE / ".bandit").exists())
        self.assertEqual([str(path) for path in PACKAGE.rglob(".bandit")], [])

    def test_empty_exception_handlers_are_written_as_suppress(self):
        offenders = []
        for path in PACKAGE.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for bad in ("except Exception:\n    pass", "except Exception:\n        pass"):
                if bad in source:
                    offenders.append(str(path.relative_to(PACKAGE)))
                    break
        self.assertEqual(offenders, [])

    def test_weak_hash_was_fixed_not_silenced(self):
        settings = (PACKAGE / "core" / "settings.py").read_text()
        self.assertIn("usedforsecurity=False", settings)


class EscapeHatchTest(unittest.TestCase):
    def test_exec_lives_in_exactly_one_place(self):
        users = [
            str(path.relative_to(PACKAGE))
            for path in PACKAGE.rglob("*.py")
            if re.search(r"(?<![.\w])exec\(", path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(users, ["qgis_tools/python/sandbox.py"])

    def test_the_suppression_is_narrow_and_stays_narrow(self):
        suppressions = [
            f"{path.relative_to(PACKAGE)}:{number}"
            for path in PACKAGE.rglob("*.py")
            for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1)
            if "nosec" in line
        ]
        self.assertEqual(suppressions, ["qgis_tools/python/sandbox.py:70"])

    def test_the_tool_running_code_asks_the_user_first(self):
        from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
        from ai_agent.qgis_tools.python.run_python import RunPythonTool

        self.assertEqual(RunPythonTool().safety, SAFETY_DESTRUCTIVE)


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
