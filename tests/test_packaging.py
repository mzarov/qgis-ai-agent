import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

import build_plugin
import check_secrets

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
METADATA = REPO_ROOT / "ai_agent" / "metadata.txt"
SECRET_BASELINE = REPO_ROOT / ".secrets.baseline"
TESTS_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"
REAL_QGIS_SMOKE = REPO_ROOT / "tests" / "real_qgis_smoke.py"
REQUIRED_METADATA_KEYS = (
    "name",
    "qgisMinimumVersion",
    "description",
    "about",
    "version",
    "author",
    "email",
    "repository",
)


def metadata_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in METADATA.read_text(encoding="utf-8").split("\n"):
        if "=" in line and not line.startswith(" "):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


class MetadataTest(unittest.TestCase):
    def setUp(self):
        self.values = metadata_values()

    def test_required_keys_are_present(self):
        missing = [key for key in REQUIRED_METADATA_KEYS if not self.values.get(key)]
        self.assertEqual(missing, [])

    def test_version_matches_pyproject(self):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{self.values["version"]}"', pyproject)

    def test_declared_qgis_version_matches_the_syntax_we_use(self):
        self.assertGreaterEqual(float(self.values["qgisMinimumVersion"]), 4.0)

    def test_icon_exists(self):
        self.assertTrue((REPO_ROOT / "ai_agent" / self.values["icon"]).is_file())

    def test_source_tree_uses_only_the_svg_brand_icon(self):
        self.assertEqual(self.values["icon"], "icon.svg")
        self.assertFalse((REPO_ROOT / "ai_agent" / "icon.png").exists())


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.archive = pathlib.Path(build_plugin.build(self.root))
        with zipfile.ZipFile(self.archive) as archive:
            self.names = archive.namelist()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_single_top_level_folder_named_after_the_package(self):
        tops = {name.split("/")[0] for name in self.names}
        self.assertEqual(tops, {build_plugin.PLUGIN_NAME})

    def test_every_skill_body_is_packed(self):
        on_disk = sorted(path.parent.name for path in (REPO_ROOT / "ai_agent").rglob("SKILL.md"))
        packed = sorted(name.rsplit("/", 2)[1] for name in self.names if name.endswith("SKILL.md"))
        self.assertTrue(on_disk, "в исходниках не найдено ни одного SKILL.md")
        self.assertEqual(packed, on_disk)

    def test_metadata_and_entry_point_are_packed(self):
        for tail in ("metadata.txt", "__init__.py", "plugin.py", "icon.svg"):
            self.assertTrue(any(name.endswith(tail) for name in self.names), tail)

    def test_development_files_stay_out(self):
        unwanted = [
            name
            for name in self.names
            if "CLAUDE.md" in name
            or "__pycache__" in name
            or name.endswith(".pyc")
            or "/tests/" in name
            or "/docs/" in name
        ]
        self.assertEqual(unwanted, [])

    def test_package_uses_an_explicit_runtime_allowlist(self):
        self.assertFalse(build_plugin.is_package_file_allowed(".env"))
        self.assertFalse(build_plugin.is_package_file_allowed("keys.json"))
        self.assertFalse(build_plugin.is_package_file_allowed("icon.png"))
        self.assertFalse(build_plugin.is_package_file_allowed("skills/CLAUDE.md"))
        self.assertTrue(build_plugin.is_package_file_allowed("core/agent/loop.py"))
        self.assertTrue(build_plugin.is_package_file_allowed("skills/inspect/SKILL.md"))

    def test_build_is_reproducible_and_uses_the_requested_directory(self):
        second = pathlib.Path(build_plugin.build(os.path.join(self.root, "second")))
        first_hash = hashlib.sha256(self.archive.read_bytes()).digest()
        second_hash = hashlib.sha256(second.read_bytes()).digest()
        self.assertEqual(self.archive.parent, pathlib.Path(self.root))
        self.assertEqual(first_hash, second_hash)
        with zipfile.ZipFile(self.archive) as archive:
            self.assertEqual({item.date_time for item in archive.infolist()}, {build_plugin.ARCHIVE_TIMESTAMP})

    def test_extracted_plugin_imports_and_builds(self):
        zipfile.ZipFile(self.archive).extractall(self.root)
        sys.path.insert(0, self.root)
        stale = [name for name in sys.modules if name.startswith(build_plugin.PLUGIN_NAME)]
        saved = {name: sys.modules.pop(name) for name in stale}
        try:
            package = __import__(build_plugin.PLUGIN_NAME)
            self.assertTrue(package.__file__.startswith(self.root))
            self.assertIsNotNone(package.classFactory(object()))
        finally:
            for name in [n for n in sys.modules if n.startswith(build_plugin.PLUGIN_NAME)]:
                del sys.modules[name]
            sys.modules.update(saved)
            sys.path.remove(self.root)

    def test_skills_load_from_the_extracted_copy(self):
        zipfile.ZipFile(self.archive).extractall(self.root)
        skills_root = os.path.join(self.root, build_plugin.PLUGIN_NAME, "skills")
        from ai_agent.skills.registry import SkillRegistry

        registry = SkillRegistry(skills_root)
        on_disk = sorted(path.parent.name for path in (REPO_ROOT / "ai_agent").rglob("SKILL.md"))
        self.assertEqual(sorted(registry.names()), on_disk)


class SecretScanTest(unittest.TestCase):
    def test_empty_detect_secrets_report_passes(self):
        self.assertEqual(check_secrets.findings({"results": {}}), [])

    def test_any_detected_secret_is_a_finding(self):
        payload = {"results": {"ai_agent/example.py": [{"line_number": 3, "type": "Secret Keyword"}]}}
        self.assertEqual(
            check_secrets.findings(payload),
            [("ai_agent/example.py", 3, "Secret Keyword")],
        )

    def test_malformed_report_is_not_treated_as_clean(self):
        with self.assertRaises(ValueError):
            check_secrets.findings({})
        with self.assertRaises(ValueError):
            check_secrets.findings({"results": {"file.py": ["not a finding"]}})

    def test_ci_scans_every_tracked_file_with_keyword_detection(self):
        workflow = TESTS_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("git ls-files -z", workflow)
        self.assertIn("detect-secrets-hook --baseline .secrets.baseline", workflow)
        self.assertNotIn("--disable-plugin KeywordDetector", workflow)

    def test_secret_baseline_is_narrow_and_audited(self):
        baseline = json.loads(SECRET_BASELINE.read_text(encoding="utf-8"))
        plugins = {item["name"] for item in baseline["plugins_used"]}
        self.assertIn("KeywordDetector", plugins)
        findings = [finding for entries in baseline["results"].values() for finding in entries]
        self.assertEqual(len(findings), 6)
        self.assertTrue(all(finding.get("is_secret") is False for finding in findings))


class RealQgisCiTest(unittest.TestCase):
    def test_minimum_and_stable_qgis_images_are_exercised(self):
        workflow = TESTS_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('qgis_image: ["4.0-trixie", "stable-trixie"]', workflow)

    def test_live_smoke_imports_the_built_archive(self):
        source = REAL_QGIS_SMOKE.read_text(encoding="utf-8")
        self.assertIn("build_plugin.build(root)", source)
        self.assertIn("archive.extractall(installation)", source)
        self.assertIn("ai_agent.__file__", source)
        self.assertIn("snapshot preserves unsaved identity", source)
        self.assertIn("active edit buffer blocks snapshot", source)
        self.assertIn("duplicate layer names are rejected", source)


if __name__ == "__main__":
    unittest.main()
