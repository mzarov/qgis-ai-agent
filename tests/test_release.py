import configparser
import pathlib
import unittest

from tools import release_notes

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
LIVE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "live-model.yml"


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

    def test_nothing_is_published_before_the_real_qgis_scenarios_pass(self):
        self.assertIn("needs: [real-qgis, live-model]", self.text)
        self.assertIn("!failure() && !cancelled()", self.text)
        self.assertIn("tests/real_qgis_workflows.py", self.text)

    def job(self, name, following):
        return self.text[self.text.index(f"\n  {name}:\n") : self.text.index(f"\n  {following}:\n")]

    def test_only_the_release_job_can_write_and_the_qgis_container_keeps_no_token(self):
        top = self.text[: self.text.index("\njobs:")]
        self.assertIn("\npermissions:\n  contents: read\n", top)
        real_qgis = self.job("real-qgis", "live-model")
        self.assertNotIn("contents: write", real_qgis)
        self.assertIn("persist-credentials: false", real_qgis)
        release = self.text[self.text.index("\n  release:\n") :]
        self.assertIn("    permissions:\n      contents: write\n", release)

    def test_the_release_gate_covers_the_minimum_qgis_and_the_type_check(self):
        real_qgis = self.job("real-qgis", "live-model")
        self.assertIn('qgis_image: ["4.0-trixie", "stable-trixie"]', real_qgis)
        self.assertIn("image: qgis/qgis:${{ matrix.qgis_image }}", real_qgis)
        self.assertIn("poetry run mypy", self.text)
        self.assertLess(self.text.index("poetry run mypy"), self.text.index("plugins.qgis.org/plugins/api/"))

    def test_the_live_model_check_spends_tokens_only_when_ticked(self):
        choice = self.text[self.text.index("live_model_check:") : self.text.index("\nconcurrency:")]
        self.assertIn("default: false", choice)


class LiveModelWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = LIVE_WORKFLOW.read_text(encoding="utf-8")

    def test_real_tokens_are_never_spent_on_push_or_pull_requests(self):
        triggers = self.text[self.text.index("\non:") : self.text.index("\nconcurrency:")]
        self.assertNotIn("push", triggers)
        self.assertNotIn("pull_request", triggers)

    def test_the_key_comes_from_a_secret_and_spending_is_capped(self):
        self.assertIn("secrets.LIVE_MODEL_KEY", self.text)
        for cap in ("timeout-minutes:", "LIVE_TOTAL_TOKENS:", "LIVE_RUN_TOKENS:"):
            self.assertIn(cap, self.text)

    def test_the_provider_is_a_setting_not_part_of_the_workflow(self):
        self.assertIn("LIVE_MODEL_URL: ${{ vars.LIVE_MODEL_URL }}", self.text)
        self.assertIn("LIVE_MODEL: ${{ vars.LIVE_MODEL }}", self.text)


if __name__ == "__main__":
    unittest.main()
