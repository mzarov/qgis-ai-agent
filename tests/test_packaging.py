import os
import pathlib
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

import build_plugin

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
METADATA = REPO_ROOT / "metadata.txt"
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
        self.assertTrue((REPO_ROOT / self.values["icon"]).is_file())


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.archive = pathlib.Path(build_plugin.build())
        self.names = zipfile.ZipFile(self.archive).namelist()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_single_top_level_folder_named_after_the_package(self):
        tops = {name.split("/")[0] for name in self.names}
        self.assertEqual(tops, {build_plugin.PLUGIN_NAME})

    def test_skill_bodies_are_packed(self):
        packed = [name for name in self.names if name.endswith("SKILL.md")]
        self.assertEqual(len(packed), 3)

    def test_metadata_and_entry_point_are_packed(self):
        for tail in ("metadata.txt", "__init__.py", "core/plugin.py", "icon.png"):
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
        skills_root = os.path.join(
            self.root, build_plugin.PLUGIN_NAME, "src", build_plugin.PLUGIN_NAME, "skills"
        )
        from qgis_ai_agent.skills.registry import SkillRegistry

        registry = SkillRegistry(skills_root)
        self.assertEqual(sorted(registry.names()), ["inspect", "processing", "style"])


if __name__ == "__main__":
    unittest.main()
