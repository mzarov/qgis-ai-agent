import unittest

from qgis.core import QgsVectorLayer

from ai_agent.core.orchestrator.presentation import (
    active_layer_chip,
    applied_summary,
    compact_number,
    interrupted_outcome,
    where_to_look,
)


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

    def test_several_new_layers_are_counted(self):
        results = [Result("run_processing", payload={"result_layer_name": name}) for name in ("Buffer", "Centroids")]
        self.assertEqual(applied_summary(results), "2 new layers")


class AfterApplyTest(unittest.TestCase):
    def test_new_layers_are_named_and_unnamed_outputs_point_to_the_panel(self):
        made = [Result("run_processing", payload={"result_layer_name": "Buffer"}), Result("set_opacity")]
        self.assertEqual(where_to_look(made), " New layers: «Buffer».")
        self.assertEqual(
            where_to_look([Result("run_processing", payload={"outputs": {}})]), " The result is in the layer panel."
        )
        self.assertEqual(where_to_look([Result("set_opacity")]), "")

    def test_a_stop_reports_what_was_done_and_nothing_when_nothing_was(self):
        results = [Result("run_processing", payload={"result_layer_name": "Buffer"}), Result("set_symbol", ok=False)]
        self.assertEqual(
            interrupted_outcome(results),
            "Stopped after 1 completed step; pending steps were cancelled. New layers: «Buffer».",
        )
        self.assertEqual(interrupted_outcome([Result("set_symbol", ok=False)]), "")

    def test_token_counts_read_short(self):
        self.assertEqual((compact_number(950), compact_number(21_340)), ("950", "21.3k"))


class CountedLayer(QgsVectorLayer):
    def __init__(self, provider, count=12):
        self.provider = provider
        self.count = count
        self.counted = 0

    def name(self):
        return "roads"

    def providerType(self):
        return self.provider

    def featureCount(self):
        self.counted += 1
        return self.count


class Iface:
    def __init__(self, layer):
        self.layer = layer

    def activeLayer(self):
        return self.layer


class ActiveLayerChipTest(unittest.TestCase):
    def test_a_local_layer_shows_its_feature_count(self):
        self.assertEqual(active_layer_chip(Iface(CountedLayer("ogr"))), ("roads", "12 features"))

    def test_a_remote_layer_is_named_but_never_counted(self):
        for provider in ("postgres", "WFS"):
            layer = CountedLayer(provider)
            self.assertEqual(active_layer_chip(Iface(layer)), ("roads", ""))
            self.assertEqual(layer.counted, 0, provider)


if __name__ == "__main__":
    unittest.main()
