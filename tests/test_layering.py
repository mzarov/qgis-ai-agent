import ast
import pathlib
import unittest

SOURCE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "src" / "qgis_ai_agent"
PACKAGE = "qgis_ai_agent"
FORBIDDEN = {
    "core": ("ui",),
    "qgis_tools": ("core", "ui"),
    "ui": ("qgis_tools", "skills"),
    "skills": ("core", "ui", "qgis_tools"),
}
DOMAINS = ("inspect", "style", "processing", "project", "osm")
COMPOSITION_ROOT = "plugin.py"


def internal_imports(path: pathlib.Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(PACKAGE):
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(
                alias.name for alias in node.names if alias.name.startswith(PACKAGE)
            )
    return found


def layer_of(path: pathlib.Path) -> str:
    relative = path.relative_to(SOURCE_ROOT)
    return relative.parts[0] if len(relative.parts) > 1 else ""


class LayeringTest(unittest.TestCase):
    def test_layers_never_import_upward(self):
        problems = []
        for path in SOURCE_ROOT.rglob("*.py"):
            source_layer = layer_of(path)
            for module in internal_imports(path):
                target_layer = module.split(".")[1] if "." in module else ""
                if target_layer in FORBIDDEN.get(source_layer, ()):
                    problems.append(f"{path.relative_to(SOURCE_ROOT)} -> {module}")
        self.assertEqual(problems, [])

    def test_composition_root_is_the_only_top_level_module(self):
        top_modules = sorted(
            item.name
            for item in SOURCE_ROOT.iterdir()
            if item.suffix == ".py" and item.name != "__init__.py"
        )
        self.assertEqual(top_modules, [COMPOSITION_ROOT])

    def test_tool_domains_do_not_import_each_other(self):
        problems = []
        for domain in DOMAINS:
            for path in (SOURCE_ROOT / "qgis_tools" / domain).rglob("*.py"):
                for module in internal_imports(path):
                    for other in DOMAINS:
                        if other != domain and f"qgis_tools.{other}" in module:
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
        layers = {item.name for item in SOURCE_ROOT.iterdir() if item.is_dir()}
        for source, targets in FORBIDDEN.items():
            self.assertIn(source, layers)
            for target in targets:
                self.assertIn(target, layers)


if __name__ == "__main__":
    unittest.main()
