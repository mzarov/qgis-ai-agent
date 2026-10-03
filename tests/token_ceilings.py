"""Token ceilings: what a scenario may spend before CI calls it a regression.

`tests/data/token_ceilings.json` holds two sections:

- `live`: per live-model scenario (`real_qgis_live`), the most prompt tokens,
  completion tokens, total tokens and model requests one scenario may use,
  verification run included. They are measured on one model and only enforced
  for that model; a local run against another model just reports.
- `scripted`: for the scripted-model scenarios (`real_qgis_e2e`), in
  characters: the largest system prompt and the largest tool schema list one
  request may carry, and `base_chars`, both together in a request before any
  skill is loaded — what every run pays at least. Deterministic, so it runs on
  every push for free.

Refresh from reports the runs produced (see docs/smoke_checklist.md):

    python3 tests/token_ceilings.py live_usage.json [more live_usage.json ...]
    python3 tests/token_ceilings.py request_sizes.json

Several live reports are merged by taking the largest value per metric, so a
ceiling built from a few runs absorbs the model's run-to-run spread; scenarios
absent from the reports keep their current ceilings. Pure standard library.
"""

import json
import math
import pathlib
import re
import sys
from typing import Any

CEILINGS_FILE = pathlib.Path(__file__).resolve().parent / "data" / "token_ceilings.json"
LIVE_HEADROOM = 1.3
SCRIPTED_HEADROOM = 1.1
TOKEN_ROUNDING = 1000
CHAR_ROUNDING = 100
LIVE_METRICS = ("prompt_tokens", "completion_tokens", "total_tokens", "requests")
SCRIPTED_METRICS = ("system_chars", "tools_chars", "base_chars")
LIVE_KIND = "live"
SCRIPTED_KIND = "scripted"
# Yandex AI Studio model URIs carry the cloud folder: gpt://<folder>/<model>.
MODEL_URI_PREFIX = re.compile(r"^[a-z]+://[^/]+/")


def model_name(model: str) -> str:
    """The model id without a provider URI scheme and folder."""
    return MODEL_URI_PREFIX.sub("", model.strip())


def load(path: pathlib.Path = CEILINGS_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def exceeded(measured: dict[str, int], ceiling: dict[str, int]) -> list[str]:
    """One line per metric over its ceiling; metrics without a ceiling are not checked."""
    return [
        f"{metric} {measured.get(metric, 0)} > ceiling {limit}"
        for metric, limit in ceiling.items()
        if measured.get(metric, 0) > limit
    ]


def live_ceiling(ceilings: dict[str, Any], model: str, scenario: str) -> dict[str, int]:
    """The ceiling for one live scenario, or {} when it is not enforced for this model."""
    live = ceilings.get(LIVE_KIND) or {}
    if model_name(model) != live.get("model"):
        return {}
    return dict((live.get("scenarios") or {}).get(scenario) or {})


def _round_up(value: float, step: int) -> int:
    return int(math.ceil(value / step) * step)


def refreshed_live(current: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    """The `live` section rebuilt from live_usage.json reports of one model."""
    models = {model_name(report.get("model", "")) for report in reports}
    if len(models) != 1:
        raise ValueError(f"reports come from different models: {sorted(models)}")
    model = models.pop()
    scenarios = dict(current.get("scenarios") or {}) if current.get("model") == model else {}
    peaks: dict[str, dict[str, int]] = {}
    for report in reports:
        for scenario, usage in (report.get("scenarios") or {}).items():
            peak = peaks.setdefault(scenario, {})
            for metric in LIVE_METRICS:
                peak[metric] = max(peak.get(metric, 0), int(usage.get(metric, 0)))
    for scenario, peak in peaks.items():
        scenarios[scenario] = {
            metric: math.ceil(value * LIVE_HEADROOM)
            if metric == "requests"
            else _round_up(value * LIVE_HEADROOM, TOKEN_ROUNDING)
            for metric, value in peak.items()
        }
    return {"model": model, "headroom": LIVE_HEADROOM, "scenarios": dict(sorted(scenarios.items()))}


def refreshed_scripted(report: dict[str, Any]) -> dict[str, int]:
    """The `scripted` section rebuilt from a request_sizes.json report."""
    return {metric: _round_up(int(report[metric]) * SCRIPTED_HEADROOM, CHAR_ROUNDING) for metric in SCRIPTED_METRICS}


def refresh(paths: list[pathlib.Path], target: pathlib.Path = CEILINGS_FILE) -> dict[str, Any]:
    """Rewrite the ceilings file from report files; returns the new content."""
    ceilings = load(target) if target.exists() else {}
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    live = [report for report in reports if report.get("kind") == LIVE_KIND]
    scripted = [report for report in reports if report.get("kind") == SCRIPTED_KIND]
    if len(live) + len(scripted) != len(reports):
        raise ValueError('every report needs "kind": "live" or "scripted"')
    if live:
        ceilings[LIVE_KIND] = refreshed_live(ceilings.get(LIVE_KIND) or {}, live)
    if scripted:
        peak = {metric: max(int(report[metric]) for report in scripted) for metric in SCRIPTED_METRICS}
        ceilings[SCRIPTED_KIND] = refreshed_scripted(peak)
    target.write_text(json.dumps(ceilings, indent=2) + "\n", encoding="utf-8")
    return ceilings


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    print(json.dumps(refresh([pathlib.Path(arg) for arg in argv]), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
