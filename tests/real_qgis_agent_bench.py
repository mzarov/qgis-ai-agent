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
from e2e_model import ScriptedModel, call, say  # noqa: E402
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
        self.assertEqual(layers["roads"]["feature_count"], 30)
        self.assertEqual((layers["stations"]["crs"], layers["stations"]["feature_count"]), ("EPSG:32637", 9))
        self.assertEqual(layers["dem"]["kind"], "raster")
        self.assertEqual(result["state"]["new_layers"], [])
        self.assertEqual(problems_in(result, {"answer": "re:\\bfive\\b"}), [])

    def test_a_task_is_applied_and_its_outcome_read_back(self) -> None:
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            say("The districts will be half transparent."),
            say("Checked: the districts are at 50 % opacity."),
        )
        result = self.runner.run({"request": "Make the districts half transparent"})
        self.assertNotIn("error", result, result.get("error"))
        self.assertFalse(result["pending"], "the bench did not press Apply")
        self.assertIn("set_opacity", [item["name"] for item in result["calls"]])
        self.assertEqual(problems_in(result, {"layers": {"districts": {"opacity": 0.5}}}), [])
        self.assertGreaterEqual(result["usage"]["requests"], 3)
        self.assertTrue(result["log"], "the plugin's log lines did not reach the task's answer")
        self.assertIn("districts is", " ".join(problems_in(result, {"layers": {"districts": {"opacity": 0.3}}})))

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
