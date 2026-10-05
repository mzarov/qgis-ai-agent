import os
import tempfile
import unittest
from unittest import mock

from ai_agent.core.agent import quick_check
from ai_agent.qgis_tools.common.layers import LAYER_PINS_KEY
from ai_agent.qgis_tools.fields import manage_fields
from ai_agent.qgis_tools.project import (
    configure_layer,
    configure_project,
    remember,
    remove_layer,
    reorder_layers,
    save_project,
    views,
)
from ai_agent.qgis_tools.registry import get_tool_by_name
from ai_agent.qgis_tools.tables import remove_join


class Call:
    def __init__(self, name, arguments=None):
        self.name = name
        self.arguments = arguments or {}


class Result:
    def __init__(self, name, ok=True, arguments=None, payload=None):
        self.call = Call(name, arguments)
        self.ok = ok
        self.payload = payload or {}


class Judge:
    def __init__(self, verdict):
        self.verdict = verdict

    def confirm_applied(self, params, payload):
        if isinstance(self.verdict, Exception):
            raise self.verdict
        return self.verdict


class ConfirmedByReadingTest(unittest.TestCase):
    def judged(self, *verdicts, ok=True):
        tools = {f"tool{index}": Judge(verdict) for index, verdict in enumerate(verdicts)}
        results = [Result(name, ok=ok) for name in tools]
        with mock.patch.object(quick_check, "get_tool_by_name", side_effect=tools.get):
            return quick_check.confirmed_by_reading(results)

    def test_every_step_read_back_skips_the_model(self):
        self.assertTrue(self.judged(True, True))

    def test_one_step_that_cannot_judge_or_did_not_take_sends_the_batch_to_the_model(self):
        self.assertFalse(self.judged(True, None))
        self.assertFalse(self.judged(True, False))
        self.assertFalse(self.judged(True, RuntimeError("wrapped C/C++ object has been deleted")))

    def test_a_failed_step_an_unknown_tool_or_an_empty_batch_is_never_confirmed(self):
        self.assertFalse(self.judged(True, ok=False))
        with mock.patch.object(quick_check, "get_tool_by_name", return_value=None):
            self.assertFalse(quick_check.confirmed_by_reading([Result("gone")]))
        self.assertFalse(quick_check.confirmed_by_reading([]))

    def test_visual_and_data_tools_always_leave_the_check_to_the_model(self):
        for name in ("set_symbol", "set_graduated", "set_labels", "run_processing", "add_layer", "draw_features"):
            self.assertIsNone(get_tool_by_name(name).confirm_applied({}, {}), name)


def pinned(layer_id="L1", **params):
    return {**params, LAYER_PINS_KEY: [{"name": "districts", "id": layer_id}]}


class Node:
    def __init__(self, visible=True, layer_id=""):
        self.visible = visible
        self.layer_id = layer_id

    def itemVisibilityChecked(self):
        return self.visible

    def layerId(self):
        return self.layer_id


class Layer:
    def __init__(self, name="districts", fields=(), joins=()):
        self._name = name
        self._fields = list(fields)
        self._joins = list(joins)

    def name(self):
        return self._name

    def fields(self):
        return mock.Mock(names=lambda: self._fields)

    def vectorJoins(self):
        return self._joins


class LayerStepsTest(unittest.TestCase):
    def test_configure_layer_reads_name_visibility_and_group(self):
        tool = configure_layer.ConfigureLayerTool()
        node = Node(visible=False)
        with (
            mock.patch.object(configure_layer, "pinned_layer", return_value=Layer("City roads")),
            mock.patch.object(configure_layer, "tree_node", return_value=node),
            mock.patch.object(configure_layer, "group_title", return_value="Transport"),
        ):
            done = {"name": "City roads", "visible": False, "group": "Transport"}
            self.assertTrue(tool.confirm_applied(pinned(properties=done), {}))
            self.assertFalse(tool.confirm_applied(pinned(properties={"name": "Roads"}), {}))
            self.assertFalse(tool.confirm_applied(pinned(properties={"visible": True}), {}))
            self.assertFalse(tool.confirm_applied(pinned(properties={"group": ""}), {}))
        with mock.patch.object(configure_layer, "pinned_layer", return_value=None):
            self.assertFalse(tool.confirm_applied(pinned(properties={"visible": False}), {}))

    def test_remove_layer_is_done_once_the_pinned_id_is_gone(self):
        tool = remove_layer.RemoveLayerTool()
        project = mock.Mock()
        with mock.patch.object(remove_layer, "project", return_value=project):
            project.mapLayer.return_value = None
            self.assertTrue(tool.confirm_applied(pinned(), {}))
            project.mapLayer.return_value = Layer()
            self.assertFalse(tool.confirm_applied(pinned(), {}))
        self.assertIsNone(tool.confirm_applied({"layer_name": "districts"}, {}))

    def test_reorder_reads_the_top_of_the_tree(self):
        tool = reorder_layers.ReorderLayersTool()
        params = {LAYER_PINS_KEY: [{"name": "a", "id": "A"}, {"name": "b", "id": "B"}]}
        root = mock.Mock()
        with mock.patch.object(reorder_layers, "layer_tree", return_value=root):
            root.children.return_value = [Node(layer_id="A"), Node(layer_id="B"), Node(layer_id="C")]
            self.assertTrue(tool.confirm_applied(params, {}))
            root.children.return_value = [Node(layer_id="B"), Node(layer_id="A")]
            self.assertFalse(tool.confirm_applied(params, {}))


class FieldStepsTest(unittest.TestCase):
    def test_plain_fields_read_back_and_virtual_ones_go_to_the_model(self):
        add, rename, delete = (
            manage_fields.AddFieldTool(),
            manage_fields.RenameFieldTool(),
            manage_fields.DeleteFieldTool(),
        )
        with mock.patch.object(manage_fields, "pinned_layer", return_value=Layer(fields=["name", "area_ha"])):
            self.assertTrue(add.confirm_applied(pinned(name="area_ha"), {}))
            self.assertFalse(add.confirm_applied(pinned(name="density"), {}))
            self.assertIsNone(add.confirm_applied(pinned(name="area_ha", expression="$area"), {}))
            self.assertTrue(rename.confirm_applied(pinned(name="nm", new_name="name"), {}))
            self.assertFalse(rename.confirm_applied(pinned(name="name", new_name="area_ha"), {}))
            self.assertTrue(delete.confirm_applied(pinned(name="notes"), {}))
            self.assertFalse(delete.confirm_applied(pinned(name="name"), {}))

    def test_a_removed_join_leaves_no_join_to_that_table(self):
        tool = remove_join.RemoveJoinTool()
        join = mock.Mock(joinLayerId=lambda: "T1")
        with mock.patch.object(remove_join, "pinned_layer", return_value=Layer(joins=[join])):
            self.assertFalse(tool.confirm_applied(pinned(table_id="T1"), {}))
            self.assertTrue(tool.confirm_applied(pinned(table_id="T2"), {}))


class ProjectStepsTest(unittest.TestCase):
    def test_bookmarks_themes_and_notes_read_back_by_name(self):
        with mock.patch.object(views, "_bookmark_names", return_value=["city centre"]):
            self.assertTrue(views.SaveBookmarkTool().confirm_applied({"name": "city centre"}, {}))
            self.assertFalse(views.SaveBookmarkTool().confirm_applied({"name": "harbour"}, {}))
        with mock.patch.object(views, "project_themes", return_value=["print"]):
            self.assertTrue(views.SaveMapThemeTool().confirm_applied({"name": "print"}, {}))
        store = mock.Mock(notes=lambda: ["pop2020 is people"])
        with mock.patch.object(remember, "NoteStore", return_value=store):
            self.assertTrue(remember.RememberTool().confirm_applied({"note": "pop2020 is people"}, {}))
            self.assertFalse(remember.ForgetTool().confirm_applied({"note": "pop2020 is people"}, {}))
            self.assertTrue(remember.ForgetTool().confirm_applied({"note": "old"}, {}))

    def test_project_settings_and_a_saved_file(self):
        instance = mock.Mock(title=lambda: "Atlas")
        with mock.patch.object(configure_project, "project", return_value=instance):
            self.assertTrue(
                configure_project.ConfigureProjectTool().confirm_applied({"properties": {"title": "Atlas"}}, {})
            )
            self.assertFalse(
                configure_project.ConfigureProjectTool().confirm_applied({"properties": {"title": "X"}}, {})
            )
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "p.qgz")
        tool = save_project.SaveProjectTool()
        self.assertFalse(tool.confirm_applied({}, {"saved": path}))
        open(path, "wb").close()
        self.assertTrue(tool.confirm_applied({}, {"saved": path}))


if __name__ == "__main__":
    unittest.main()
