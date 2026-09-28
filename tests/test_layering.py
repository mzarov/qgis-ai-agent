import ast
import pathlib
import unittest

SOURCE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "ai_agent"
PACKAGE = "ai_agent"
FORBIDDEN = {
    "config": ("core", "ui", "qgis_tools", "skills"),
    "core": ("ui",),
    "qgis_tools": ("core", "ui"),
    "ui": ("qgis_tools", "skills"),
    "skills": ("core", "ui", "qgis_tools"),
}
TOOL_ROOT = SOURCE_ROOT / "qgis_tools"
SHARED_TOOL_PACKAGES = {"common"}
DOMAINS = tuple(
    sorted(
        item.name
        for item in TOOL_ROOT.iterdir()
        if item.is_dir() and (item / "__init__.py").is_file() and item.name not in SHARED_TOOL_PACKAGES
    )
)
TOP_LEVEL_MODULES = ("i18n.py", "plugin.py")
LEAF_MODULES = ("i18n.py",)


def internal_imports(path: pathlib.Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(PACKAGE):
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names if alias.name.startswith(PACKAGE))
    return found


class LayeringTest(unittest.TestCase):
    def test_layers_never_import_upward(self):
        problems = []
        for source_layer, forbidden in FORBIDDEN.items():
            for path in (SOURCE_ROOT / source_layer).rglob("*.py"):
                for module in internal_imports(path):
                    target_layer = module.split(".")[1] if "." in module else ""
                    if target_layer in forbidden:
                        problems.append(f"{path.relative_to(SOURCE_ROOT)} -> {module}")
        self.assertEqual(problems, [])

    def test_only_the_composition_root_and_leaves_sit_at_the_top(self):
        top_modules = sorted(
            item.name for item in SOURCE_ROOT.iterdir() if item.suffix == ".py" and item.name != "__init__.py"
        )
        self.assertEqual(top_modules, sorted(TOP_LEVEL_MODULES))

    def test_top_level_leaves_import_nothing_of_ours(self):
        for name in LEAF_MODULES:
            self.assertEqual(internal_imports(SOURCE_ROOT / name), [], name)

    def test_tool_domains_do_not_import_each_other(self):
        problems = []
        for domain in DOMAINS:
            for path in (SOURCE_ROOT / "qgis_tools" / domain).rglob("*.py"):
                for module in internal_imports(path):
                    parts = module.split(".")
                    if len(parts) >= 3 and parts[1] == "qgis_tools":
                        target_domain = parts[2]
                        if target_domain in DOMAINS and target_domain != domain:
                            problems.append(f"{domain}/{path.name} -> {module}")
        self.assertEqual(problems, [])

    def test_skills_package_is_pure(self):
        problems = []
        for path in (SOURCE_ROOT / "skills").rglob("*.py"):
            for module in internal_imports(path):
                if not module.startswith(f"{PACKAGE}.skills"):
                    problems.append(f"{path.name} -> {module}")
        self.assertEqual(problems, [])

    def test_ui_never_touches_the_network(self):
        problems = []
        for path in (SOURCE_ROOT / "ui").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in ("requests", "QgsBlockingNetworkRequest", "post_json", "chat("):
                if marker in text:
                    problems.append(f"{path.name}: {marker}")
        self.assertEqual(problems, [])

    def test_every_forbidden_rule_names_real_layers(self):
        layers = {item.name for item in SOURCE_ROOT.iterdir() if item.is_dir() and any(item.glob("*.py"))}
        self.assertEqual(set(FORBIDDEN), layers)
        for targets in FORBIDDEN.values():
            for target in targets:
                self.assertIn(target, layers)


if __name__ == "__main__":
    unittest.main()
