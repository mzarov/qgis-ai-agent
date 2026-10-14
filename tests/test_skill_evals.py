"""The skill bench: its request is the plugin's own, its cases name real tools, its check reads calls right."""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

EVALS = Path(__file__).resolve().parent.parent / "evals"
sys.path.insert(0, str(EVALS))

import checks  # noqa: E402
import context as agent_request  # noqa: E402
import prompt as prompt_function  # noqa: E402
import run as runner  # noqa: E402
import thresholds  # noqa: E402

sys.path.insert(0, str(EVALS / "agent"))
import outcome  # noqa: E402
from agent import bench  # noqa: E402

from ai_agent.skills.registry import SKILL_REGISTRY  # noqa: E402

CALL_LINE = re.compile(r"^\s*(?:-\s*)?call:\s*(\[[^\]]*\]|[A-Za-z0-9_]+)", re.MULTILINE)
LOADS = re.compile(r"(?:loads|not_loads):\s*\[([^\]]*)\]")


def names_in(value: str) -> list[str]:
    return [item.strip() for item in value.strip("[]").split(",") if item.strip()]


class RequestTest(unittest.TestCase):
    def test_a_loaded_skill_brings_its_body_tools_and_load_call(self):
        messages, schemas = agent_request.build("style", "Colour the roads by type", ["roads", "roads/highway"])
        tools = [schema["function"]["name"] for schema in schemas]
        self.assertIn("set_categories", tools)
        self.assertIn(SKILL_REGISTRY.get("style").body.strip()[:80], messages[0]["content"])
        calls = [message["tool_calls"][0]["function"]["name"] for message in messages if message.get("tool_calls")]
        self.assertEqual(calls, ["load_skill", "describe_layer", "get_field_values"])
        self.assertIn("highway", json.dumps(messages))
        self.assertIn("Project context", messages[-1]["content"], "the per-turn state is not folded in")

    def test_the_first_turn_offers_every_skill_but_the_preloaded_one(self):
        messages, schemas = agent_request.build("", "Save the project")
        load = next(schema for schema in schemas if schema["function"]["name"] == "load_skill")
        offered = load["function"]["parameters"]["properties"]["names"]["items"]["enum"]
        self.assertNotIn("inspect", offered)
        self.assertIn("project", offered)
        self.assertEqual([message["role"] for message in messages], ["system", "user"])

    def test_an_algorithm_read_comes_from_the_fixture(self):
        messages, _ = agent_request.build("processing", "Buffer the stations", ["native:buffer"])
        self.assertIn("DISTANCE", messages[-1]["content"] + json.dumps(messages))

    def test_reads_are_a_string_or_steps_never_a_list(self):
        self.assertEqual(prompt_function.reads("roads, roads/highway"), ["roads", "roads/highway"])
        step = {"tool": "describe_style", "args": {"layer_name": "roads"}, "result": {"renderer": "single"}}
        self.assertEqual(prompt_function.reads({"steps": [step]}), [step])

    def test_the_prompt_function_returns_a_chat(self):
        text = prompt_function.build({"vars": {"skill": "fields", "request": "Add a field", "reads": "districts"}})
        self.assertEqual(json.loads(text)[0]["role"], "system")


class CasesTest(unittest.TestCase):
    def test_every_case_calls_a_tool_its_skill_offers(self):
        for suite, cases in runner.suites().items():
            skill = "" if suite == runner.ROUTING else suite
            offered = {schema["function"]["name"] for schema in agent_request.tool_schemas(skill)}
            for match in CALL_LINE.finditer(cases.read_text(encoding="utf-8")):
                for name in names_in(match.group(1)):
                    with self.subTest(suite=suite, tool=name):
                        self.assertIn(name, offered, "a case names a tool this skill does not have")

    def test_every_skill_a_case_expects_exists(self):
        known = set(SKILL_REGISTRY.names())
        for cases in runner.suites().values():
            for match in LOADS.finditer(cases.read_text(encoding="utf-8")):
                for name in names_in(match.group(1)):
                    with self.subTest(skill=name):
                        self.assertIn(name, known)

    def test_the_main_skills_have_cases(self):
        self.assertTrue({"routing", "inspect", "style", "processing", "fields", "project"} <= set(runner.suites()))

    def test_no_case_uses_a_list_for_its_reads(self):
        for suite, cases in runner.suites().items():
            with self.subTest(suite=suite):
                self.assertNotRegex(cases.read_text(encoding="utf-8"), r"reads:\s*\[")


class ChecksTest(unittest.TestCase):
    def call(self, name, **arguments):
        return {"id": "c", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}

    def test_a_call_with_the_expected_arguments_passes_leniently(self):
        output = [self.call("set_graduated", layer_name="Districts ", field="pop2020", classes="5")]
        expect = {"call": "set_graduated", "args": {"layer_name": "districts", "classes": 5}}
        self.assertTrue(checks.expected(output, {"vars": {"expect": expect}})["pass"])

    def test_a_wrong_argument_fails_and_says_what_the_model_did(self):
        result = checks.expected(
            [self.call("set_categories", layer_name="roads", field="name")],
            {"vars": {"expect": {"call": "set_categories", "args": {"field": "highway"}}}},
        )
        self.assertFalse(result["pass"])
        self.assertIn('set_categories({"layer_name": "roads", "field": "name"})', result["reason"])

    def test_nested_parameters_regexes_and_presence(self):
        arguments = {"algorithm_id": "native:buffer", "parameters": {"INPUT": "stations", "DISTANCE": 500.0}}
        self.assertTrue(checks.matches({"parameters": {"DISTANCE": 500}, "algorithm_id": "re:buffer"}, arguments))
        self.assertTrue(checks.matches({"parameters": "*"}, arguments))
        self.assertFalse(checks.matches({"parameters": {"DISTANCE": 1000}}, arguments))

    def test_a_list_is_at_least_these_against_a_list_and_any_of_against_a_value(self):
        self.assertTrue(checks.matches(["osm", "processing"], ["processing", "style", "osm"]))
        self.assertFalse(checks.matches(["osm", "processing"], ["osm"]))
        self.assertTrue(checks.matches(["native:buffer", "qgis:buffer"], "qgis:buffer"))

    def test_loads_and_forbidden_tools(self):
        output = [self.call("load_skill", names=["osm"]), self.call("update_plan", steps=["a"])]
        self.assertIsNone(checks.mismatch({"loads": ["osm"], "not": ["run_python"]}, checks.tool_calls(output)))
        self.assertIn("processing", checks.mismatch({"loads": ["osm", "processing"]}, checks.tool_calls(output)))
        self.assertIsNotNone(checks.mismatch({"not_loads": ["osm"]}, checks.tool_calls(output)))

    def test_any_of_and_an_answer_in_words(self):
        calls = checks.tool_calls([self.call("describe_processing", algorithm_id="native:reprojectlayer")])
        options = {"any_of": [{"call": "run_processing"}, {"call": "describe_processing"}]}
        self.assertIsNone(checks.mismatch(options, calls))
        self.assertIsNone(checks.mismatch({"answer": True}, checks.tool_calls("Fifty-eight schools.")))
        self.assertIsNotNone(checks.mismatch({"answer": True}, calls))

    def test_outputs_in_every_shape_promptfoo_gives(self):
        call = self.call("save_project")
        for output in ([call], {"content": "", "tool_calls": [call]}, json.dumps([call])):
            with self.subTest(output=type(output).__name__):
                self.assertEqual(checks.tool_calls(output), [("save_project", {})])


class RunnerTest(unittest.TestCase):
    def test_a_config_points_at_the_suites_tools_cases_and_check(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(runner, "OUT", Path(folder)):
            path = runner.write_config("style", runner.suites()["style"], ["m1", "m2"], "http://127.0.0.1:9/v1", "ru")
            config = json.loads(path.read_text(encoding="utf-8"))
            tools = json.loads((Path(folder) / "style.tools.json").read_text(encoding="utf-8"))
        self.assertEqual([provider["label"] for provider in config["providers"]], ["m1", "m2"])
        self.assertFalse(config["providers"][0]["config"]["apiKeyRequired"], "a local server needs no key")
        self.assertEqual(config["defaultTest"]["vars"], {"skill": "style", "locale": "ru"})
        self.assertTrue(config["tests"].endswith("skills/style/evals/cases.yaml"))
        self.assertIn("set_categories", [schema["function"]["name"] for schema in tools])

    def test_an_oauth_gateway_gets_its_header_without_the_key_on_disk(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(runner, "OUT", Path(folder)):
            path = runner.write_config(
                "fields", runner.suites()["fields"], ["m"], "https://gw.example/v1", "en", "OAuth"
            )
            text = path.read_text(encoding="utf-8")
        self.assertIn('"Authorization": "OAuth {{ env.EVAL_API_KEY }}"', text)

    def test_a_key_typed_in_a_cyrillic_layout_is_caught_before_the_run(self):
        self.assertEqual(runner.key_problem("sk-abc123"), "")
        problem = runner.key_problem("abcКey")
        self.assertIn("position 4", problem)
        self.assertNotIn("abc", problem, "the message repeats the key")

    def test_the_summary_counts_and_names_failures(self):
        rows = [
            {"success": True, "response": {"tokenUsage": {"total": 100}}, "latencyMs": 1000},
            {
                "success": False,
                "testCase": {"description": "Labels"},
                "provider": {"label": "m1"},
                "gradingResult": {"reason": "did not call set_labels"},
                "response": {"tokenUsage": {"total": 50}},
                "latencyMs": 3000,
            },
        ]
        with tempfile.TemporaryDirectory() as folder:
            results = Path(folder) / "style.results.json"
            results.write_text(json.dumps({"results": {"results": rows}}), encoding="utf-8")
            summary = runner.summarise("style", results)
        self.assertEqual((summary["passed"], summary["total"], summary["tokens"]), (1, 2, 150))
        self.assertEqual(summary["errors"], 0)
        self.assertEqual(summary["failures"], ["Labels [m1]: did not call set_labels"])
        self.assertIn("| style | 1/2 | 0 | 150 | 2.0 s |", runner.report([summary]))

    def test_a_case_that_never_reached_the_model_is_not_a_failure(self):
        rows = [
            {"success": True, "latencyMs": 1000},
            {
                "success": False,
                "error": "Connect Timeout Error",
                "failureReason": 2,
                "testCase": {"description": "Hide"},
            },
            {
                "success": False,
                "error": "did not call save_project",
                "failureReason": 1,
                "gradingResult": {"pass": False, "reason": "did not call save_project"},
                "testCase": {"description": "Save"},
            },
        ]
        with tempfile.TemporaryDirectory() as folder:
            results = Path(folder) / "project.results.json"
            results.write_text(json.dumps({"results": {"results": rows}}), encoding="utf-8")
            summary = runner.summarise("project", results)
        self.assertEqual(summary["errors"], 1, "a failed check was counted as unreached")
        self.assertIn("| project | 1/2 | 1 |", runner.report([summary]))


def row(suite, passed, total, errors=0):
    return {"suite": suite, "passed": passed, "total": total, "errors": errors}


class ThresholdsTest(unittest.TestCase):
    def test_a_floor_is_the_measured_rate_less_the_margin_rounded_down(self):
        self.assertEqual(thresholds.floor_for(0.95), 0.85)
        self.assertEqual(thresholds.floor_for(22 / 24), 0.8)
        self.assertEqual(thresholds.floor_for(0.05), 0.0)

    def test_saving_keeps_other_suites_of_the_same_model_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "thresholds.json"
            thresholds.save([row("routing", 22, 24), row("style", 10, 10)], "m1", path)
            thresholds.save([row("style", 9, 10)], "m1", path)
            self.assertEqual(thresholds.load(path)["suites"], {"routing": 0.8, "style": 0.8})
            thresholds.save([row("fields", 6, 6)], "m2", path)
            self.assertEqual(thresholds.load(path), {"model": "m2", "margin": 0.1, "suites": {"fields": 0.9}})

    def test_a_suite_below_its_floor_fails_and_unreached_cases_do_not_count(self):
        data = {"model": "m1", "suites": {"routing": 0.8, "style": 0.9}}
        problems = thresholds.check([row("routing", 18, 24), row("style", 9, 12, errors=2)], "m1", data)
        self.assertEqual(problems, ["routing: 75% passed, below its floor of 80%"])

    def test_floors_of_another_model_only_report_unless_required(self):
        data = {"model": "m1", "suites": {"routing": 0.8}}
        self.assertEqual(thresholds.check([row("routing", 1, 24)], "m2", data), [])
        self.assertTrue(thresholds.check([row("routing", 1, 24)], "m2", data, require=True))
        self.assertEqual(thresholds.check([row("charts", 0, 6)], "m1", data, require=True), ["charts: no floor yet"])

    def test_a_suite_whose_cases_never_reached_the_model_fails_its_floor(self):
        data = {"model": "m1", "suites": {"routing": 0.8}}
        self.assertEqual(
            thresholds.check([row("routing", 0, 24, errors=24)], "m1", data),
            ["routing: no case reached the model"],
        )


class WorkflowTest(unittest.TestCase):
    def test_the_ci_workflow_runs_the_bench_with_the_check_and_the_shared_provider(self):
        text = (EVALS.parent / ".github" / "workflows" / "skill-evals.yml").read_text(encoding="utf-8")
        self.assertIn("python3 evals/run.py", text)
        self.assertIn("--check", text)
        self.assertIn("secrets.LIVE_MODEL_KEY", text)
        self.assertNotRegex(text, r"(?m)^  push:", "the bench spends tokens; it must not run on every push")


def run_result(**changes):
    result = {
        "answer": "There are five.",
        "asked": False,
        "pending": False,
        "timed_out": False,
        "calls": [{"name": "query_layer", "ok": True}],
        "usage": {"prompt_tokens": 9000, "completion_tokens": 100, "requests": 2, "runs": 1},
        "seconds": 12.5,
        "failures": [],
        "state": {
            "project": {"crs": "EPSG:3857", "layouts": [], "annotations": 0},
            "layers": {"districts": {"renderer": "graduatedSymbol", "class_attribute": "pop2020", "classes": 5}},
            "new_layers": [{"name": "Buffered", "geometry": "polygon", "feature_count": 9, "crs": "EPSG:32637"}],
            "files": ["roads.gpkg"],
        },
    }
    result.update(changes)
    return result


class AgentOutcomeTest(unittest.TestCase):
    def test_an_outcome_that_matches_passes_with_its_cost(self):
        expect = {
            "answer": "re:\\bfive\\b",
            "layers": {"districts": {"renderer": "graduatedSymbol", "classes": 5}},
            "new_layers": [{"geometry": "polygon", "feature_count": 9}],
            "files": ["roads.gpkg"],
            "calls": ["query_layer"],
        }
        graded = outcome.outcome(json.dumps(run_result()), {"vars": {"expect": expect}})
        self.assertTrue(graded["pass"], graded["reason"])
        self.assertIn("12.5 s, 2 requests", graded["reason"])

    def test_a_wrong_layer_state_reads_as_a_comparison(self):
        problems = outcome.problems_in(run_result(), {"layers": {"districts": {"classes": 7}}})
        self.assertEqual(problems, ['districts is {"classes": 5}, expected {"classes": 7}'])

    def test_a_missing_new_layer_names_what_was_added(self):
        problems = outcome.problems_in(run_result(), {"new_layers": [{"geometry": "point"}]})
        self.assertIn("Buffered", problems[0])

    def test_asking_an_unapplied_batch_and_a_timeout_fail_unless_expected(self):
        self.assertEqual(outcome.problems_in(run_result(asked=True), {}), ["the agent stopped to ask"])
        self.assertEqual(outcome.problems_in(run_result(asked=True), {"asked": True}), [])
        self.assertIn("a prepared batch was left unapplied", outcome.problems_in(run_result(pending=True), {}))
        self.assertIn("the run did not finish in time", outcome.problems_in(run_result(timed_out=True), {}))

    def test_no_request_names_the_failure_instead_of_blaming_the_agent(self):
        result = run_result(usage={"requests": 0}, failures=["The key was not accepted: 401"])
        problems = outcome.problems_in(result, {"answer": "re:five"})
        self.assertEqual(len(problems), 1)
        self.assertIn("The key was not accepted", problems[0])

    def test_any_of_and_a_server_error(self):
        options = {"any_of": [{"project": {"crs": "EPSG:4326"}}, {"files": ["roads.gpkg"]}]}
        self.assertEqual(outcome.problems_in(run_result(), options), [])
        failed = outcome.problems_in({"error": "Traceback\n  line\nValueError: broken"}, {})
        self.assertIn("ValueError: broken", failed[0])


class AgentBenchConfigTest(unittest.TestCase):
    def test_the_config_posts_each_task_to_the_server_and_checks_its_outcome(self):
        with tempfile.TemporaryDirectory() as folder:
            path = bench.write_config(Path(folder), "deepseek", "http://127.0.0.1:8765")
            config = json.loads(path.read_text(encoding="utf-8"))
        provider = config["providers"][0]
        self.assertEqual((provider["id"], provider["label"]), ("http", "deepseek"))
        self.assertEqual(provider["config"]["url"], "http://127.0.0.1:8765/run")
        self.assertEqual(provider["config"]["maxRetries"], 0, "a task costs a whole agent run; never retried")
        self.assertIn("tokenUsage", provider["config"]["transformResponse"])
        self.assertTrue(config["defaultTest"]["assert"][0]["value"].endswith("outcome.py:outcome"))

    def test_the_key_reaches_the_server_by_name_only(self):
        self.assertIn("EVAL_API_KEY", bench.PASSED_ENV)
        self.assertNotIn("=", "".join(bench.PASSED_ENV))

    def test_every_task_has_a_request_and_an_expectation(self):
        text = bench.TASKS.read_text(encoding="utf-8")
        cases = text.count("- description:")
        self.assertGreaterEqual(cases, 20)
        self.assertEqual(text.count("    request:"), cases)
        self.assertEqual(text.count("    expect:"), cases)


if __name__ == "__main__":
    unittest.main()
