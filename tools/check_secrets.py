import json
import sys
from typing import Any


def findings(payload: Any) -> list[tuple[str, int, str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), dict):
        raise ValueError("detect-secrets output has no results object")
    found = []
    for path, entries in payload["results"].items():
        if not isinstance(entries, list):
            raise ValueError(f"detect-secrets returned invalid entries for {path}")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"detect-secrets returned an invalid finding for {path}")
            found.append((str(path), int(entry.get("line_number") or 0), str(entry.get("type") or "secret")))
    return found


def main(arguments: list[str] | None = None) -> int:
    arguments = list(arguments if arguments is not None else sys.argv[1:])
    if len(arguments) != 1:
        print("Usage: python3 tools/check_secrets.py <detect-secrets-report.json>", file=sys.stderr)
        return 2
    try:
        with open(arguments[0], encoding="utf-8") as handle:
            found = findings(json.load(handle))
    except (OSError, ValueError) as failure:
        print(f"Secret scan could not be verified: {failure}", file=sys.stderr)
        return 2
    for path, line, kind in found:
        print(f"Potential secret: {path}:{line} ({kind})", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
