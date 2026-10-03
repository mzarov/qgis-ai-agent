import json
import pathlib
import re
import tempfile
import unittest

from tests import token_ceilings

LIVE_SOURCE = pathlib.Path(__file__).resolve().parent / "real_qgis_live.py"
YANDEX_URI = "gpt://b1gfolder/deepseek-v4.1-flash"


def _live_report(model: str = YANDEX_URI, **scenarios: dict[str, int]) -> dict:
    return {"kind": "live", "model": model, "scenarios": scenarios}


class CheckTest(unittest.TestCase):
    def test_the_folder_is_stripped_from_a_model_uri(self):
        self.assertEqual(token_ceilings.model_name(YANDEX_URI), "deepseek-v4.1-flash")
        self.assertEqual(token_ceilings.model_name("gpt://folder/yandexgpt/latest"), "yandexgpt/latest")
        self.assertEqual(token_ceilings.model_name("qwen3"), "qwen3")

    def test_only_metrics_with_a_ceiling_are_checked(self):
        measured = {"prompt_tokens": 900, "completion_tokens": 50, "requests": 12}
        self.assertEqual(token_ceilings.exceeded(measured, {"requests": 12}), [])
        self.assertEqual(token_ceilings.exceeded(measured, {"prompt_tokens": 800}), ["prompt_tokens 900 > ceiling 800"])
        self.assertEqual(token_ceilings.exceeded(measured, {}), [])

    def test_a_ceiling_applies_only_to_its_model(self):
        ceilings = {"live": {"model": "deepseek-v4.1-flash", "scenarios": {"LiveStyleScenario": {"requests": 9}}}}
        self.assertEqual(token_ceilings.live_ceiling(ceilings, YANDEX_URI, "LiveStyleScenario"), {"requests": 9})
        self.assertEqual(token_ceilings.live_ceiling(ceilings, "qwen3", "LiveStyleScenario"), {})
        self.assertEqual(token_ceilings.live_ceiling(ceilings, YANDEX_URI, "LiveNewScenario"), {})


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.target = pathlib.Path(self.folder.name) / "ceilings.json"
        self.target.write_text(
            json.dumps(
                {
                    "live": {"model": "deepseek-v4.1-flash", "scenarios": {"LiveOldScenario": {"total_tokens": 7}}},
                    "scripted": {"system_chars": 1, "tools_chars": 1, "base_chars": 1},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.folder.cleanup()

    def refresh(self, *reports: dict) -> dict:
        paths = []
        for index, report in enumerate(reports):
            path = pathlib.Path(self.folder.name) / f"report{index}.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            paths.append(path)
        return token_ceilings.refresh(paths, self.target)

    def test_the_peak_of_several_runs_gets_the_headroom(self):
        first = {"prompt_tokens": 10_000, "completion_tokens": 900, "total_tokens": 10_900, "requests": 6}
        second = {"prompt_tokens": 20_000, "completion_tokens": 500, "total_tokens": 20_500, "requests": 4}
        result = self.refresh(_live_report(LiveStyleScenario=first), _live_report(LiveStyleScenario=second))
        self.assertEqual(
            result["live"]["scenarios"]["LiveStyleScenario"],
            {"prompt_tokens": 26_000, "completion_tokens": 2_000, "total_tokens": 27_000, "requests": 8},
        )
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")), result)

    def test_scenarios_missing_from_the_reports_keep_their_ceilings(self):
        result = self.refresh(_live_report(LiveStyleScenario={"requests": 1}))
        self.assertEqual(result["live"]["scenarios"]["LiveOldScenario"], {"total_tokens": 7})
        self.assertEqual(result["scripted"]["system_chars"], 1)

    def test_another_model_replaces_the_live_ceilings(self):
        result = self.refresh(_live_report("qwen3", LiveStyleScenario={"requests": 1}))
        self.assertEqual(result["live"]["model"], "qwen3")
        self.assertNotIn("LiveOldScenario", result["live"]["scenarios"])

    def test_requests_get_at_least_a_fixed_slack(self):
        result = self.refresh(_live_report(LiveStyleScenario={"requests": 3}))
        self.assertEqual(result["live"]["scenarios"]["LiveStyleScenario"], {"requests": 5})

    def test_unanswered_scenarios_and_unmeasured_metrics_set_no_ceiling(self):
        usage = {"total_tokens": 1_000, "requests": 1}
        result = self.refresh(_live_report(LiveStyleScenario=usage, LiveFailedScenario={"requests": 0}))
        scenarios = result["live"]["scenarios"]
        self.assertEqual(scenarios["LiveStyleScenario"], {"total_tokens": 2_000, "requests": 3})
        self.assertNotIn("LiveFailedScenario", scenarios)

    def test_an_old_report_without_the_split_is_ignored(self):
        report = _live_report()
        report["scenarios"] = {"LiveStyleScenario": 48_000}
        result = self.refresh(report)
        self.assertNotIn("LiveStyleScenario", result["live"]["scenarios"])

    def test_reports_of_different_models_are_refused(self):
        with self.assertRaises(ValueError):
            self.refresh(_live_report("qwen3"), _live_report(YANDEX_URI))

    def test_a_report_without_a_kind_is_refused(self):
        with self.assertRaises(ValueError):
            self.refresh({"scenarios": {}})

    def test_scripted_sizes_get_their_own_headroom(self):
        result = self.refresh({"kind": "scripted", "system_chars": 20_000, "tools_chars": 9_910, "base_chars": 100})
        self.assertEqual(result["scripted"], {"system_chars": 22_000, "tools_chars": 11_000, "base_chars": 200})
        self.assertEqual(result["live"]["scenarios"], {"LiveOldScenario": {"total_tokens": 7}})


class CheckedInCeilingsTest(unittest.TestCase):
    def test_every_live_scenario_has_a_ceiling_and_every_ceiling_a_scenario(self):
        scenarios = set(re.findall(r"^class (Live\w+Scenario)\(LiveCase\):", LIVE_SOURCE.read_text(), re.MULTILINE))
        self.assertTrue(scenarios)
        self.assertEqual(set(token_ceilings.load()["live"]["scenarios"]), scenarios)

    def test_ceilings_name_known_metrics_only(self):
        ceilings = token_ceilings.load()
        for scenario, ceiling in ceilings["live"]["scenarios"].items():
            self.assertTrue(ceiling, scenario)
            self.assertLessEqual(set(ceiling), set(token_ceilings.LIVE_METRICS), scenario)
        self.assertEqual(set(ceilings["scripted"]), set(token_ceilings.SCRIPTED_METRICS))
        self.assertNotIn("://", ceilings["live"]["model"], "the model id must not carry the cloud folder")


if __name__ == "__main__":
    unittest.main()
