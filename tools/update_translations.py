import ast
import pathlib
import sys
import xml.etree.ElementTree as ElementTree

from qm import compile_qm

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "qgis_ai_agent"
FOLDER = PACKAGE / "translations"
CONTEXT = "QgisAiAgent"
PREFIX = "qgis_ai_agent"
LANGUAGES = ("ru",)
CALLS = ("tr", "tr_n")
UNFINISHED = "unfinished"
PLURAL_FORMS = 3
SUFFIX = ".qm"
HEADER = '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'


def sources() -> list[tuple[str, str, int, bool]]:
    found: list[tuple[str, str, int, bool]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = _called_name(node.func)
            if name not in CALLS:
                continue
            argument = node.args[0]
            if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                raise SystemExit(f"{path}:{node.lineno}: {name}() needs a literal string")
            location = str(path.relative_to(PACKAGE.parent))
            found.append((argument.value, location, node.lineno, name == "tr_n"))
    return found


def _called_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    return getattr(func, "attr", "")


def existing(path: pathlib.Path) -> dict[str, tuple[list[str], bool]]:
    if not path.is_file():
        return {}
    known: dict[str, tuple[list[str], bool]] = {}
    for message in ElementTree.parse(path).getroot().iter("message"):
        source = message.findtext("source") or ""
        target = message.find("translation")
        if target is None:
            continue
        forms = [form.text or "" for form in target.findall("numerusform")]
        known[source] = (forms or [target.text or ""], target.get("type") == UNFINISHED)
    return known


def build(language: str, entries: list[tuple[str, str, int, bool]]) -> str:
    known = existing(FOLDER / f"{PREFIX}_{language}.ts")
    lines = [HEADER, f'<TS version="2.1" language="{language}">\n<context>\n']
    lines.append(f"    <name>{CONTEXT}</name>\n")
    seen: dict[str, list[tuple[str, int]]] = {}
    plural: dict[str, bool] = {}
    for text, location, lineno, is_plural in entries:
        seen.setdefault(text, []).append((location, lineno))
        plural[text] = plural.get(text, False) or is_plural
    for text in sorted(seen):
        forms, unfinished = known.get(text, ([""], True))
        lines.append('    <message numerus="yes">\n' if plural[text] else "    <message>\n")
        for location, lineno in seen[text]:
            lines.append(f'        <location filename="{location}" line="{lineno}"/>\n')
        lines.append(f"        <source>{_escaped(text)}</source>\n")
        lines.append(_translation(forms, unfinished, plural[text]))
        lines.append("    </message>\n")
    lines.append("</context>\n</TS>\n")
    return "".join(lines)


def _translation(forms: list[str], unfinished: bool, is_plural: bool) -> str:
    filled = [form for form in forms if form]
    mark = f' type="{UNFINISHED}"' if unfinished or not filled else ""
    if not is_plural:
        return f"        <translation{mark}>{_escaped(forms[0])}</translation>\n"
    padded = (forms + [""] * PLURAL_FORMS)[:PLURAL_FORMS]
    body = "".join(f"            <numerusform>{_escaped(form)}</numerusform>\n" for form in padded)
    return f"        <translation{mark}>\n{body}        </translation>\n"


def _escaped(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "&#10;")


def translated(path: pathlib.Path) -> list[tuple[str, str, list[str]]]:
    root = ElementTree.parse(path).getroot()
    messages: list[tuple[str, str, list[str]]] = []
    for block in root.iter("context"):
        context = block.findtext("name") or CONTEXT
        for message in block.iter("message"):
            target = message.find("translation")
            if target is None or target.get("type") == UNFINISHED:
                continue
            forms = [form.text or "" for form in target.findall("numerusform")]
            messages.append((context, message.findtext("source") or "", forms or [target.text or ""]))
    return messages


def compile_all() -> None:
    for language in LANGUAGES:
        target = FOLDER / f"{PREFIX}_{language}{SUFFIX}"
        messages = translated(FOLDER / f"{PREFIX}_{language}.ts")
        target.write_bytes(compile_qm(language, messages))
        print(f"compiled {target.relative_to(REPO_ROOT)}: {len(messages)} messages")


def main() -> int:
    FOLDER.mkdir(parents=True, exist_ok=True)
    entries = sources()
    for language in LANGUAGES:
        path = FOLDER / f"{PREFIX}_{language}.ts"
        path.write_text(build(language, entries), encoding="utf-8")
        print(f"{path.relative_to(REPO_ROOT)}: {len({text for text, _, _, _ in entries})} strings")
    compile_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
