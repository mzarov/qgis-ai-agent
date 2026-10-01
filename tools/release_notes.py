"""Print the changelog entry of one version from metadata.txt, as Markdown.

Used by the release workflow for the GitHub release body. Without an argument
it prints the entry of the version in metadata.txt.

Run: python3 tools/release_notes.py [version]
"""

import configparser
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METADATA = os.path.join(REPO_ROOT, "ai_agent", "metadata.txt")
VERSION_LINE = re.compile(r"^\d+\.\d+\.\d+\S*$")


def read_metadata(path: str = METADATA) -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    with open(path, encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser["general"]


def notes_for(version: str, changelog: str) -> list[str]:
    """Bullet lines of one version; the changelog lists versions newest first."""
    lines = [line.strip() for line in changelog.splitlines()]
    collected: list[str] = []
    inside = False
    for line in lines:
        if VERSION_LINE.match(line):
            if inside:
                break
            inside = line == version
            continue
        if inside and line:
            collected.append(line)
    return collected


def main(argv: list[str]) -> int:
    general = read_metadata()
    version = argv[1] if len(argv) > 1 else general["version"].strip()
    notes = notes_for(version, general.get("changelog", ""))
    if not notes:
        print(f"No changelog entry for {version} in metadata.txt", file=sys.stderr)
        return 1
    print("\n".join(notes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
