import ast
import builtins
import os
import unittest

SOURCE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
)
KNOWN = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__"}
MAX_LINES = 200


def python_files():
    for folder, _, names in os.walk(SOURCE_ROOT):
        if "__pycache__" in folder:
            continue
        for name in sorted(names):
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def module_scope(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def local_scope(func):
    names = {arg.arg for arg in func.args.args + func.args.kwonlyargs}
    if func.args.vararg:
        names.add(func.args.vararg.arg)
    if func.args.kwarg:
        names.add(func.args.kwarg.arg)
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.comprehension):
            names.update(sub.id for sub in ast.walk(node.target) if isinstance(sub, ast.Name))
        elif isinstance(node, ast.Lambda):
            names.update(arg.arg for arg in node.args.args + node.args.kwonlyargs)
    return names


class UndefinedNameTest(unittest.TestCase):
    def test_no_undefined_names(self):
        problems = []
        for path in python_files():
            tree = ast.parse(open(path, encoding="utf-8").read())
            known = module_scope(tree) | KNOWN
            functions = [n for n in ast.walk(tree)
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for func in functions:
                scope = known | local_scope(func) | {"self", "cls"}
                for node in ast.walk(func):
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                        if node.id not in scope:
                            problems.append(f"{path}:{node.lineno} {node.id}")
        self.assertEqual(sorted(set(problems)), [])


class StyleTest(unittest.TestCase):
    def test_no_comments_and_no_docstrings(self):
        problems = []
        for path in python_files():
            source = open(path, encoding="utf-8").read()
            for number, line in enumerate(source.split("\n"), 1):
                if line.strip().startswith("#"):
                    problems.append(f"{path}:{number} комментарий")
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                    body = getattr(node, "body", [])
                    first = body[0] if body else None
                    if (isinstance(first, ast.Expr)
                            and isinstance(getattr(first, "value", None), ast.Constant)
                            and isinstance(first.value.value, str)):
                        problems.append(f"{path}:{first.lineno} docstring")
        self.assertEqual(problems, [])

    def test_files_stay_under_the_limit(self):
        too_long = []
        for path in python_files():
            lines = len(open(path, encoding="utf-8").read().split("\n"))
            if lines > MAX_LINES:
                too_long.append(f"{os.path.basename(path)}: {lines}")
        self.assertEqual(too_long, [])

    def test_imports_are_absolute(self):
        relative = []
        for path in python_files():
            for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
                if isinstance(node, ast.ImportFrom) and node.level:
                    relative.append(f"{path}:{node.lineno}")
        self.assertEqual(relative, [])


if __name__ == "__main__":
    unittest.main()
