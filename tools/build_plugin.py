import os
import sys
import zipfile

PLUGIN_NAME = "qgis_ai_agent"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(REPO_ROOT, "dist")
ROOT_FILES = ("__init__.py", "metadata.txt", "icon.png", "LICENSE")
SOURCE_DIR = "src"
SKIPPED_DIRS = {"__pycache__", ".git", ".mypy_cache", ".ruff_cache"}
SKIPPED_NAMES = {"CLAUDE.md", ".DS_Store"}
SKIPPED_SUFFIXES = (".pyc", ".pyo")
REQUIRED_INSIDE = ("skills/inspect/SKILL.md", "skills/style/SKILL.md", "skills/processing/SKILL.md")


def read_version() -> str:
    path = os.path.join(REPO_ROOT, "metadata.txt")
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("В metadata.txt нет строки version=")


def is_wanted(name: str) -> bool:
    if name in SKIPPED_NAMES:
        return False
    return not name.endswith(SKIPPED_SUFFIXES)


def collect() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for name in ROOT_FILES:
        absolute = os.path.join(REPO_ROOT, name)
        if not os.path.isfile(absolute):
            raise SystemExit(f"Не найден обязательный файл {name}")
        entries.append((absolute, f"{PLUGIN_NAME}/{name}"))
    for folder, dirs, names in os.walk(os.path.join(REPO_ROOT, SOURCE_DIR)):
        dirs[:] = sorted(item for item in dirs if item not in SKIPPED_DIRS)
        for name in sorted(names):
            if not is_wanted(name):
                continue
            absolute = os.path.join(folder, name)
            relative = os.path.relpath(absolute, REPO_ROOT)
            entries.append((absolute, f"{PLUGIN_NAME}/{relative}"))
    return entries


def verify(entries: list[tuple[str, str]]) -> None:
    packed = {arc for _, arc in entries}
    missing = [
        tail for tail in REQUIRED_INSIDE
        if not any(arc.endswith(tail) for arc in packed)
    ]
    if missing:
        raise SystemExit("В сборку не попало обязательное: " + ", ".join(missing))
    entry_point = f"{PLUGIN_NAME}/src/{PLUGIN_NAME}/plugin.py"
    if entry_point not in packed:
        raise SystemExit(f"В сборку не попала точка входа {entry_point}")


def build() -> str:
    entries = collect()
    verify(entries)
    os.makedirs(DIST_DIR, exist_ok=True)
    target = os.path.join(DIST_DIR, f"{PLUGIN_NAME}-{read_version()}.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for absolute, arcname in entries:
            archive.write(absolute, arcname)
    return target


def main() -> None:
    target = build()
    size_kb = os.path.getsize(target) / 1024
    with zipfile.ZipFile(target) as archive:
        count = len(archive.namelist())
    print(f"Собрано: {os.path.relpath(target, REPO_ROOT)}")
    print(f"Файлов: {count}, размер: {size_kb:.0f} КБ")
    print(f"Корневая папка в архиве: {PLUGIN_NAME}/")


if __name__ == "__main__":
    sys.exit(main())
