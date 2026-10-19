import argparse
import csv
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PLUGIN_URL = "https://plugins.qgis.org/plugins/{slug}/json"
TRAFFIC_URL = "https://api.github.com/repos/{repo}/traffic/{kind}"
PLUGIN_SLUG = "ai_agent"
DOWNLOADS_FILE = "downloads.csv"
TRAFFIC_FILE = "traffic.csv"
CHART_FILE = "daily_downloads.svg"
README_FILE = "README.md"
DOWNLOADS_HEADER = ["day", "version", "downloads", "uploaded"]
TRAFFIC_HEADER = ["day", "views", "unique_views", "clones", "unique_clones"]
TIMEOUT_S = 30
CHART_DAYS = 60
TABLE_DAYS = 14
CHART_WIDTH, CHART_HEIGHT = 720, 240
MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 44, 12, 28, 28
BAR_COLOUR = "#4C78C8"
INK = "#8B8F98"
BAR_GAP = 2


def fetch_json(url: str, token: str = "") -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "ai-agent-metrics", "Accept": "application/json"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # nosec B310 - fixed https URLs
        return json.loads(response.read().decode("utf-8"))


def plugin_rows(payload: dict[str, Any], day: str) -> list[dict[str, str]]:
    return [
        {
            "day": day,
            "version": str(version.get("version", "")),
            "downloads": str(int(version.get("downloads") or 0)),
            "uploaded": str(version.get("upload_datetime") or "")[:10],
        }
        for version in payload.get("versions") or []
    ]


def traffic_rows(views: dict[str, Any], clones: dict[str, Any]) -> list[dict[str, str]]:
    days: dict[str, dict[str, str]] = {}
    for kind, payload in (("views", views), ("clones", clones)):
        for entry in payload.get(kind) or []:
            day = str(entry.get("timestamp", ""))[:10]
            row = days.setdefault(day, dict.fromkeys(TRAFFIC_HEADER, "0") | {"day": day})
            row[kind] = str(int(entry.get("count") or 0))
            row[f"unique_{kind}"] = str(int(entry.get("uniques") or 0))
    return [days[day] for day in sorted(days)]


def merge_rows(path: Path, header: list[str], rows: list[dict[str, str]], key: tuple[str, ...]) -> list[dict[str, str]]:
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                merged[tuple(row[name] for name in key)] = row
    for row in rows:
        merged[tuple(row[name] for name in key)] = row
    ordered = [merged[item] for item in sorted(merged)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(ordered)
    return ordered


def daily_downloads(rows: list[dict[str, str]]) -> list[tuple[str, int, int | None]]:
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["day"]] = totals.get(row["day"], 0) + int(row["downloads"])
    series: list[tuple[str, int, int | None]] = []
    previous: int | None = None
    for day in sorted(totals):
        series.append((day, totals[day], None if previous is None else totals[day] - previous))
        previous = totals[day]
    return series


def render_chart(series: list[tuple[str, int, int | None]]) -> str:
    points = [(day, new) for day, _, new in series if new is not None][-CHART_DAYS:]
    plot_w = CHART_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    plot_h = CHART_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    top = max([new for _, new in points] + [1])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" '
        f'font-family="-apple-system, Segoe UI, sans-serif" font-size="11">',
        f'<text x="{MARGIN_LEFT}" y="16" fill="{INK}" font-size="12">New downloads per day, plugins.qgis.org</text>',
        f'<line x1="{MARGIN_LEFT}" y1="{MARGIN_TOP + plot_h}" x2="{CHART_WIDTH - MARGIN_RIGHT}" '
        f'y2="{MARGIN_TOP + plot_h}" stroke="{INK}" stroke-width="1"/>',
        f'<text x="{MARGIN_LEFT - 6}" y="{MARGIN_TOP + 4}" fill="{INK}" text-anchor="end">{top}</text>',
        f'<text x="{MARGIN_LEFT - 6}" y="{MARGIN_TOP + plot_h}" fill="{INK}" text-anchor="end">0</text>',
    ]
    if not points:
        parts.append(
            f'<text x="{CHART_WIDTH / 2}" y="{MARGIN_TOP + plot_h / 2}" fill="{INK}" text-anchor="middle">'
            "The second daily snapshot starts the series.</text>"
        )
    slot = plot_w / max(len(points), 1)
    width = max(slot - BAR_GAP, 1.0)
    for index, (day, new) in enumerate(points):
        height = plot_h * max(new, 0) / top
        x = MARGIN_LEFT + index * slot + BAR_GAP / 2
        y = MARGIN_TOP + plot_h - height
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="1.5" fill="{BAR_COLOUR}">'
            f"<title>{day}: {new}</title></rect>"
        )
    for index, (day, _) in enumerate(points):
        if index in (0, len(points) - 1):
            x = MARGIN_LEFT + index * slot + slot / 2
            parts.append(f'<text x="{x:.1f}" y="{CHART_HEIGHT - 8}" fill="{INK}" text-anchor="middle">{day[5:]}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def render_readme(
    versions: list[dict[str, str]], series: list[tuple[str, int, int | None]], traffic: list[dict[str, str]]
) -> str:
    latest_day = max((row["day"] for row in versions), default="")
    lines = [
        "# AI Agent — public metrics",
        "",
        "Collected once a day by `.github/workflows/metrics.yml` on `main` (`tools/collect_metrics.py`). "
        "Downloads come from plugins.qgis.org: a version's count includes updates, so the first days after "
        "a release roughly show how many installs are in use. Traffic is GitHub's own count of the repository.",
        "",
        f"![New downloads per day]({CHART_FILE})",
        "",
        f"## Downloads by version, {latest_day}",
        "",
        "| version | published | downloads |",
        "| --- | --- | --- |",
    ]
    current = sorted((row for row in versions if row["day"] == latest_day), key=lambda row: row["uploaded"])
    lines += [f"| {row['version']} | {row['uploaded']} | {row['downloads']} |" for row in reversed(current)]
    lines += ["", "## Last days", "", "| day | total | new |", "| --- | --- | --- |"]
    for day, total, new in series[-TABLE_DAYS:][::-1]:
        lines.append(f"| {day} | {total} | {'—' if new is None else new} |")
    if traffic:
        lines += ["", "## GitHub traffic", "", "| day | views (unique) | clones (unique) |", "| --- | --- | --- |"]
        for row in traffic[-TABLE_DAYS:][::-1]:
            lines.append(
                f"| {row['day']} | {row['views']} ({row['unique_views']}) | {row['clones']} ({row['unique_clones']}) |"
            )
    return "\n".join(lines) + "\n"


def collect(data: Path, repo: str, token: str, today: str) -> None:
    data.mkdir(parents=True, exist_ok=True)
    payload = fetch_json(PLUGIN_URL.format(slug=PLUGIN_SLUG))
    versions = merge_rows(data / DOWNLOADS_FILE, DOWNLOADS_HEADER, plugin_rows(payload, today), ("day", "version"))
    traffic: list[dict[str, str]] = []
    if token:
        try:
            views = fetch_json(TRAFFIC_URL.format(repo=repo, kind="views"), token)
            clones = fetch_json(TRAFFIC_URL.format(repo=repo, kind="clones"), token)
            traffic = merge_rows(data / TRAFFIC_FILE, TRAFFIC_HEADER, traffic_rows(views, clones), ("day",))
        except urllib.error.HTTPError as error:
            print(f"Traffic skipped: GitHub answered {error.code}; the token needs Administration: read.")
    else:
        print("Traffic skipped: no METRICS_TOKEN.")
    series = daily_downloads(versions)
    (data / CHART_FILE).write_text(render_chart(series), encoding="utf-8")
    (data / README_FILE).write_text(render_readme(versions, series, traffic), encoding="utf-8")
    print(f"Downloads on {today}: {series[-1][1] if series else 0} in all.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Append today's public metrics to the metrics folder.")
    parser.add_argument("--data", required=True, type=Path, help="checkout of the metrics branch")
    parser.add_argument("--repo", default="mzarov/qgis-ai-agent", help="owner/name for GitHub traffic")
    arguments = parser.parse_args(argv)
    today = datetime.datetime.now(datetime.UTC).date().isoformat()
    collect(arguments.data, arguments.repo, os.environ.get("TRAFFIC_TOKEN", "").strip(), today)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
