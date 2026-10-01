import configparser
import pathlib
import unittest

from tools import release_notes

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


class MetadataParsesTest(unittest.TestCase):
    def test_metadata_is_valid_ini_for_the_plugin_repository(self):
        parser = configparser.ConfigParser(interpolation=None)
        with open(release_notes.METADATA, encoding="utf-8") as handle:
            parser.read_file(handle)
        self.assertIn("version", parser["general"])

    def test_the_current_version_has_release_notes(self):
        general = release_notes.read_metadata()
        notes = release_notes.notes_for(general["version"].strip(), general["changelog"])
        self.assertTrue(notes)
        self.assertTrue(all(line.startswith("- ") for line in notes))


class NotesForTest(unittest.TestCase):
    CHANGELOG = "0.2.0\n- new\n- more\n0.1.0\n- old\n"

    def test_only_the_asked_version_is_returned(self):
        self.assertEqual(release_notes.notes_for("0.2.0", self.CHANGELOG), ["- new", "- more"])
        self.assertEqual(release_notes.notes_for("0.1.0", self.CHANGELOG), ["- old"])

    def test_an_unknown_version_has_no_notes(self):
        self.assertEqual(release_notes.notes_for("9.9.9", self.CHANGELOG), [])


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_the_store_upload_comes_before_the_tag(self):
        self.assertLess(self.text.index("plugins.qgis.org/plugins/api/"), self.text.index("gh release create"))

    def test_the_token_comes_from_a_secret_only(self):
        self.assertIn("secrets.QGIS_PLUGIN_TOKEN", self.text)
        self.assertIn("Authorization: Bearer ${QGIS_PLUGIN_TOKEN}", self.text)

    def test_releases_run_only_from_main_after_the_tests(self):
        self.assertIn("refs/heads/main", self.text)
        self.assertLess(self.text.index("unittest discover"), self.text.index("build_plugin.py"))


if __name__ == "__main__":
    unittest.main()
