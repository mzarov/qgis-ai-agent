"""The agent bench's server in live QGIS, against the scripted model: fixture, run, Apply, snapshot, check.

The bench itself needs a real model; this proves its plumbing on every CI run:
the fixture holds the numbers the tasks rely on, a task's writes are applied,
and the snapshot reads back what the outcome check expects.
"""

import pathlib
import sys
import unittest

AGENT_BENCH = pathlib.Path(__file__).resolve().parent.parent / "evals" / "agent"
sys.path.insert(0, str(AGENT_BENCH))

import server  # noqa: E402
from e2e_model import ScriptedModel, call, calls, say  # noqa: E402
from outcome import problems_in  # noqa: E402

MODEL = "agent-bench-fixture"


class AgentBenchServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.model = ScriptedModel().start()
        self.runner = server.Runner(self.model.url, MODEL, check_images=False)

    def tearDown(self) -> None:
        self.model.stop()

    def test_the_fixture_holds_the_numbers_the_tasks_rely_on(self) -> None:
        self.model.script(say("There are five."))
        result = self.runner.run({"request": "How many schools have a capacity above 1000?"})
        self.assertNotIn("error", result, result.get("error"))
        layers = result["state"]["layers"]
        self.assertEqual(layers["schools"]["feature_count"], 24)
        self.assertEqual(layers["schools"]["sums"]["capacity"], 15910)
        self.assertEqual(layers["schools"]["sums"]["fid"], 300, "the schools are not the 24 the tasks count on")
        self.assertEqual(layers["districts"]["sums"]["pop2020"], 993209)
        self.assertEqual(problems_in(result, {"layers": {"districts": {"measured_km2": "~335.8±0.1%"}}}), [])
        self.assertEqual(result["state"]["project"]["layouts"], [])
        self.assertEqual(layers["roads"]["feature_count"], 30)
        self.assertEqual((layers["stations"]["crs"], layers["stations"]["feature_count"]), ("EPSG:32637", 9))
        self.assertEqual(layers["dem"]["kind"], "raster")
        self.assertEqual(result["state"]["new_layers"], [])
        self.assertEqual(layers["districts"]["symbol_opacity"], 1.0)
        self.assertEqual(problems_in(result, {"answer": "re:\\bfive\\b"}), [])

    def test_an_unanswered_picture_check_is_asked_once_more(self) -> None:
        answers = iter([None, False])
        self.runner._images_pending = True
        self.runner.probe_images = lambda overrides: next(answers)
        self.runner._check_images()
        self.assertIs(self.runner.sees_images, False, "a dropped picture request left the answer unknown")

    def test_a_task_is_applied_and_its_outcome_read_back(self) -> None:
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            say("The districts will be half transparent."),
        )
        result = self.runner.run({"request": "Make the districts half transparent"})
        self.assertNotIn("error", result, result.get("error"))
        self.assertFalse(result["pending"], "the bench did not press Apply")
        self.assertIn("set_opacity", [item["name"] for item in result["calls"]])
        self.assertEqual(problems_in(result, {"layers": {"districts": {"opacity": 0.5}}}), [])
        self.assertGreaterEqual(result["usage"]["requests"], 3)
        steps = [step for step in result["steps"] if step["name"] == "set_opacity"]
        self.assertEqual(steps[0]["result"], "queued")
        self.assertIn('"opacity": 0.5', steps[0]["args"])
        self.assertEqual(steps[1], {"name": "set_opacity", "applied": "ok"}, "what Apply did is not recorded")
        self.assertTrue(result["log"], "the plugin's log lines did not reach the task's answer")
        self.assertIn("districts is", " ".join(problems_in(result, {"layers": {"districts": {"opacity": 0.3}}})))

    def test_the_map_renders_for_the_agents_look(self) -> None:
        self.model.script(
            call("describe_layer", layer_name="nowhere"), call("render_map"), say("The map shows the districts.")
        )
        result = self.runner.run({"request": "Show me the map"})
        self.assertNotIn("error", result, result.get("error"))
        self.assertEqual(result["calls"][-1], {"name": "render_map", "ok": True}, result["log"])
        self.assertTrue(result["steps"][0]["result"].startswith("error: "), "the error the model read is not kept")
        self.assertIn("nowhere", result["steps"][0]["result"] + result["steps"][0]["args"])

    def test_a_virtual_field_is_summed_with_the_others(self) -> None:
        self.model.script(
            call("load_skill", names=["fields"]),
            calls(("add_field", {"layer_name": "districts", "name": "area_ha", "expression": "$area / 10000"})),
            say("The field is ready."),
            say("Checked."),
        )
        result = self.runner.run({"request": "Add a field area_ha with each district's area in hectares"})
        self.assertNotIn("error", result, result.get("error"))
        # The fixture's ellipsoid makes $area metres on the layer in degrees, as in a new desktop project.
        self.assertEqual(problems_in(result, {"layers": {"districts": {"sums": {"area_ha": "~33580±1%"}}}}), [])

    def test_a_new_layer_is_seen_with_its_points(self) -> None:
        self.model.script(
            call("load_skill", names=["draw"]),
            call(
                "draw_features",
                geometry="point",
                new_layer_name="Red Square",
                features=[{"coordinates": [[37.6208, 55.7539]], "attributes": {}}],
            ),
            say("A point for Red Square is ready."),
            say("Checked."),
        )
        result = self.runner.run({"request": "Put a point at 55.7539, 37.6208 and call it Red Square"})
        self.assertNotIn("error", result, result.get("error"))
        expect = {
            "new_layers": [{"geometry": "point", "feature_count": 1, "points_wgs84": "re:\\[37\\.6208, 55\\.7539\\]"}]
        }
        self.assertEqual(problems_in(result, expect), [])


if __name__ == "__main__":
    unittest.main()
