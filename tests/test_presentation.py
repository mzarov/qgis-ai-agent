"""What the status line says an apply changed."""

import unittest

from ai_agent.core.orchestrator.presentation import applied_summary


class Call:
    def __init__(self, name, **arguments):
        self.name = name
        self.arguments = arguments


class Result:
    def __init__(self, name, ok=True, payload=None, **arguments):
        self.call = Call(name, **arguments)
        self.ok = ok
        self.payload = payload or {}


class AppliedSummaryTest(unittest.TestCase):
    def test_a_restyle_of_one_layer_is_a_redraw(self):
        results = [
            Result("set_graduated", layer_name="districts"),
            Result("set_labels", layer_name="districts"),
        ]
        self.assertEqual(applied_summary(results), "Layer “districts” redrawn")

    def test_another_change_of_one_layer_is_a_change(self):
        self.assertEqual(applied_summary([Result("configure_layer", layer_name="roads")]), "Layer “roads” changed")

    def test_a_new_layer_is_named(self):
        result = Result("run_processing", payload={"result_layer_name": "Station zones"})
        self.assertEqual(applied_summary([result]), "New layer “Station zones”")

    def test_several_layers_are_counted(self):
        results = [Result("set_opacity", layer_name="roads"), Result("set_opacity", layer_name="rivers")]
        self.assertEqual(applied_summary(results), "2 layers changed")

    def test_changes_without_a_layer_are_counted_and_failed_steps_left_out(self):
        results = [Result("configure_project"), Result("zoom_to_layer", ok=False, layer_name="roads")]
        self.assertEqual(applied_summary(results), "1 change applied")
        self.assertEqual(applied_summary([Result("set_opacity", ok=False, layer_name="roads")]), "")


if __name__ == "__main__":
    unittest.main()
