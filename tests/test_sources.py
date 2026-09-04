import ast
import pathlib
import unittest

SOURCE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "ai_agent"


class SourceContractTest(unittest.TestCase):
    def test_every_function_declares_its_return_type(self):
        bare = []
        for path in SOURCE_ROOT.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.FunctionDef) and node.returns is None and not node.name.startswith("__"):
                    bare.append(f"{path.relative_to(SOURCE_ROOT)}:{node.lineno} {node.name}")
        self.assertEqual(bare, [])

    def test_imports_are_absolute(self):
        relative = []
        for path in SOURCE_ROOT.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.level:
                    relative.append(f"{path.relative_to(SOURCE_ROOT)}:{node.lineno}")
        self.assertEqual(relative, [])


if __name__ == "__main__":
    unittest.main()
