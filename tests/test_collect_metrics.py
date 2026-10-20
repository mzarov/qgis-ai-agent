import contextlib
import io
import sys
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import collect_metrics  # noqa: E402

PLUGIN = {
    "downloads": 1613,
    "versions": [
        {"version": "0.3.0", "downloads": 87, "upload_datetime": "2026-10-13T07:52:40"},
        {"version": "0.2.0", "downloads": 498, "upload_datetime": "2026-10-04T15:07:38"},
    ],
}
VIEWS = {"views": [{"timestamp": "2026-10-15T00:00:00Z", "count": 7, "uniques": 3}]}
CLONES = {"clones": [{"timestamp": "2026-10-15T00:00:00Z", "count": 40, "uniques": 9}]}


class MetricsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())

    def test_a_snapshot_keeps_each_versions_total(self) -> None:
        rows = collect_metrics.plugin_rows(PLUGIN, "2026-10-16")
        self.assertEqual(
            rows[0], {"day": "2026-10-16", "version": "0.3.0", "downloads": "87", "uploaded": "2026-10-13"}
        )

    def test_a_rerun_on_the_same_day_replaces_its_rows(self) -> None:
        path = self.folder / "downloads.csv"
        header = collect_metrics.DOWNLOADS_HEADER
        collect_metrics.merge_rows(path, header, collect_metrics.plugin_rows(PLUGIN, "2026-10-16"), ("day", "version"))
        later = {**PLUGIN, "versions": [{**PLUGIN["versions"][0], "downloads": 90}, PLUGIN["versions"][1]]}
        rows = collect_metrics.merge_rows(
            path, header, collect_metrics.plugin_rows(later, "2026-10-16"), ("day", "version")
        )
        self.assertEqual(len(rows), 2)
        self.assertIn("90", [row["downloads"] for row in rows])

    def test_new_downloads_are_the_difference_between_snapshots(self) -> None:
        rows = collect_metrics.plugin_rows(PLUGIN, "2026-10-15")
        rows += collect_metrics.plugin_rows(
            {"versions": [{**PLUGIN["versions"][0], "downloads": 120}, PLUGIN["versions"][1]]}, "2026-10-16"
        )
        self.assertEqual(collect_metrics.daily_downloads(rows), [("2026-10-15", 585, None), ("2026-10-16", 618, 33)])

    def test_traffic_merges_views_and_clones_by_day(self) -> None:
        self.assertEqual(
            collect_metrics.traffic_rows(VIEWS, CLONES),
            [{"day": "2026-10-15", "views": "7", "unique_views": "3", "clones": "40", "unique_clones": "9"}],
        )

    def test_the_chart_is_valid_svg_with_or_without_a_series(self) -> None:
        for series in ([], [("2026-10-15", 585, None), ("2026-10-16", 618, 33)]):
            with self.subTest(len(series)):
                root = ElementTree.fromstring(collect_metrics.render_chart(series))
                self.assertTrue(root.tag.endswith("svg"))

    def test_a_run_without_a_token_collects_downloads_only(self) -> None:
        printed = io.StringIO()
        with (
            mock.patch.object(collect_metrics, "fetch_json", return_value=PLUGIN) as fetch,
            contextlib.redirect_stdout(printed),
        ):
            collect_metrics.collect(self.folder, "owner/repo", "", "2026-10-16")
        self.assertIn("no METRICS_TOKEN", printed.getvalue())
        fetch.assert_called_once()
        readme = (self.folder / "README.md").read_text(encoding="utf-8")
        self.assertIn("| 0.3.0 | 2026-10-13 | 87 |", readme)
        self.assertNotIn("GitHub traffic", readme)
        self.assertTrue((self.folder / "daily_downloads.svg").exists())

    def test_a_plugin_page_without_versions_fails_and_adds_no_day(self):
        downloads = self.folder / "downloads.csv"
        downloads.write_text("day,version,downloads,uploaded\n2026-10-19,0.4.0,48,2026-10-17\n", encoding="utf-8")
        for payload in ({"plugin": {"name": "AI Agent"}, "releases": []}, {"versions": []}, {"versions": "0.4.0"}):
            with (
                self.subTest(payload=payload),
                mock.patch.object(collect_metrics, "fetch_json", return_value=payload),
                self.assertRaisesRegex(ValueError, "no versions"),
            ):
                collect_metrics.collect(self.folder, "owner/repo", "", "2026-10-20")
        self.assertNotIn("2026-10-20", downloads.read_text(encoding="utf-8"))
        self.assertFalse((self.folder / "README.md").exists())

    def test_the_run_exits_with_an_error_when_the_downloads_are_missing(self):
        errors = io.StringIO()
        with (
            mock.patch.object(collect_metrics, "fetch_json", return_value={}),
            contextlib.redirect_stderr(errors),
        ):
            self.assertEqual(collect_metrics.main(["--data", str(self.folder)]), 1)
        self.assertIn("::error::", errors.getvalue())

    def test_a_traffic_timeout_still_keeps_the_days_downloads(self):
        for failure in (urllib.error.URLError(TimeoutError("timed out")), TimeoutError("The read operation timed out")):

            def fetch(url, token="", failure=failure):
                if "plugins.qgis.org" in url:
                    return PLUGIN
                raise failure

            printed = io.StringIO()
            with (
                self.subTest(failure=type(failure).__name__),
                mock.patch.object(collect_metrics, "fetch_json", side_effect=fetch),
                contextlib.redirect_stdout(printed),
            ):
                collect_metrics.collect(self.folder, "owner/repo", "token", "2026-10-16")
            self.assertIn("Traffic skipped", printed.getvalue())
            self.assertIn("2026-10-16,0.3.0,87", (self.folder / "downloads.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
