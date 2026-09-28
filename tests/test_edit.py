import copy
import unittest
from unittest.mock import patch

from qgis.core import QgsVectorLayer

from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.llm.transport import ToolCall
from ai_agent.qgis_tools.common import layers as layers_module
from ai_agent.qgis_tools.edit import delete_features as delete_module
from ai_agent.qgis_tools.edit import update_attributes as update_module
from ai_agent.qgis_tools.edit.delete_features import DeleteFeaturesTool
from ai_agent.qgis_tools.edit.update_attributes import UpdateAttributesTool


class Fields:
    def __init__(self, names):
        self._names = list(names)

    def names(self):
        return list(self._names)

    def indexFromName(self, name):
        return self._names.index(name) if name in self._names else -1


class Feature:
    def __init__(self, fid, attributes):
        self._id = fid
        self.attributes = attributes

    def id(self):
        return self._id


class EditableLayer(QgsVectorLayer):
    def __init__(self, names, rows, commit_ok=True):
        self._fields = Fields(names)
        self._features = [Feature(fid, dict(attrs)) for fid, attrs in rows]
        self._commit_ok = commit_ok
        self.editing = False
        self.rolled_back = False
        self.changes = []
        self.commit_calls = 0
        self._before = None

    def name(self):
        return "Дороги"

    def id(self):
        return "roads_stable_id"

    def fields(self):
        return self._fields

    def getFeatures(self, request=None):
        return iter(list(self._features))

    def startEditing(self):
        self._before = copy.deepcopy(self._features)
        self.editing = True
        return True

    def isEditable(self):
        return self.editing

    def changeAttributeValue(self, fid, index, value):
        self.changes.append((fid, index, value))
        for feature in self._features:
            if feature.id() == fid:
                feature.attributes[self._fields.names()[index]] = value
        return True

    def deleteFeatures(self, ids):
        wanted = set(ids)
        self._features = [feature for feature in self._features if feature.id() not in wanted]
        return True

    def commitChanges(self):
        self.commit_calls += 1
        if self._commit_ok:
            self.editing = False
        return self._commit_ok

    def commitErrors(self):
        return ["disk full"]

    def rollBack(self):
        self.rolled_back = True
        self.editing = False
        self._features = self._before
        return True


class EditTestBase(unittest.TestCase):
    def setUp(self):
        self.layer = EditableLayer(
            ["name", "type"], [(1, {"name": "a", "type": "old"}), (2, {"name": "b", "type": "old"})]
        )
        self._saved = []
        for module in (update_module, delete_module):
            self._saved.append((module, module.find_layer_by_name, module.find_layer_by_id, module.build_request))
            module.find_layer_by_name = lambda name: self.layer
            module.find_layer_by_id = lambda identifier: self.layer
            module.build_request = lambda text, layer=None: None

    def tearDown(self):
        for module, finder, id_finder, builder in self._saved:
            module.find_layer_by_name = finder
            module.find_layer_by_id = id_finder
            module.build_request = builder


class UpdateAttributesTest(EditTestBase):
    def setUp(self):
        super().setUp()
        self.tool = UpdateAttributesTool()

    def test_unknown_field_is_rejected_with_a_hint(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "values": {"tpye": "x"}})
        self.assertIn("tpye", str(caught.exception))

    def test_empty_values_are_rejected(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_name": "Дороги", "values": {}})

    def test_prepare_counts_the_matches(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertEqual(prepared["matched_estimate"], 2)
        self.assertEqual(prepared["layer_id"], "roads_stable_id")
        self.assertEqual(prepared["_feature_ids"], [1, 2])

    def test_apply_uses_the_layer_id_bound_during_prepare(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "values": {"type": "new"}})
        update_module.find_layer_by_name = lambda name: (_ for _ in ()).throw(AssertionError("name lookup used"))
        result = self.tool.execute(prepared)
        self.assertEqual(result["updated"], 2)

    def test_execute_changes_every_matching_feature(self):
        result = self.tool.execute({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertEqual(result["updated"], 2)
        self.assertTrue(all(f.attributes["type"] == "new" for f in self.layer._features))

    def test_apply_updates_only_the_feature_ids_bound_during_prepare(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "values": {"type": "new"}})
        self.layer._features.append(Feature(3, {"name": "c", "type": "old"}))
        result = self.tool.execute(prepared)
        self.assertEqual(result["updated"], 2)
        self.assertEqual(self.layer._features[-1].attributes["type"], "old")

    def test_missing_prepared_feature_aborts_before_editing(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "values": {"type": "new"}})
        self.layer._features = self.layer._features[:1]
        with self.assertRaisesRegex(ValueError, "no longer exist"):
            self.tool.execute(prepared)
        self.assertFalse(self.layer.editing)

    def test_failed_commit_rolls_back_and_reports(self):
        self.layer._commit_ok = False
        with self.assertRaises(ValueError) as caught:
            self.tool.execute({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertTrue(self.layer.rolled_back)
        self.assertIn("disk full", str(caught.exception))
        self.assertIn("may already contain partial changes", str(caught.exception))
        self.assertNotIn("nothing changed", str(caught.exception))

    def test_refused_attribute_update_rolls_back_earlier_changes(self):
        change = self.layer.changeAttributeValue

        def update_or_refuse(fid, index, value):
            return change(fid, index, value) if fid == 1 else False

        with (
            patch.object(self.layer, "changeAttributeValue", side_effect=update_or_refuse),
            self.assertRaisesRegex(ValueError, "refused to update"),
        ):
            self.tool.execute({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertTrue(self.layer.rolled_back)
        self.assertEqual(self.layer.commit_calls, 0)
        self.assertTrue(all(feature.attributes["type"] == "old" for feature in self.layer._features))

    def test_attribute_exception_closes_the_owned_edit_session(self):
        with (
            patch.object(self.layer, "changeAttributeValue", side_effect=RuntimeError("provider failure")),
            self.assertRaisesRegex(ValueError, "provider failure"),
        ):
            self.tool.execute({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertTrue(self.layer.rolled_back)
        self.assertFalse(self.layer.editing)
        self.assertEqual(self.layer.commit_calls, 0)

    def test_manual_edit_session_is_preserved(self):
        self.layer.startEditing()
        self.layer.changeAttributeValue(1, 1, "manual")
        with self.assertRaisesRegex(ValueError, "already has an active edit session"):
            self.tool.execute({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertTrue(self.layer.editing)
        self.assertFalse(self.layer.rolled_back)
        self.assertEqual(self.layer.commit_calls, 0)
        self.assertEqual(self.layer._features[0].attributes["type"], "manual")

    def test_batch_accepts_an_id_that_disambiguates_duplicate_names(self):
        other = EditableLayer(["type"], [(1, {"type": "other"})])
        other.id = lambda: "other_id"
        project = type(
            "Project",
            (),
            {
                "mapLayers": lambda _: {other.id(): other, self.layer.id(): self.layer},
                "mapLayersByName": lambda _, name: [other, self.layer],
            },
        )()
        holder = type("ProjectHolder", (), {"instance": staticmethod(lambda: project)})
        with patch.object(layers_module, "QgsProject", holder):
            for include_name in (False, True):
                with self.subTest(include_name=include_name):
                    arguments = {"layer_id": self.layer.id(), "values": {"type": "new"}}
                    if include_name:
                        arguments["layer_name"] = self.layer.name()
                    queued = WriteBatch(ToolExecutor()).add(ToolCall("update", "update_attributes", arguments))
                    self.assertEqual(queued.arguments["layer_id"], self.layer.id())
                    self.assertEqual(layers_module.layer_pin_error(queued.arguments), "")

    def test_summary_shows_the_count_and_never_raises(self):
        summary = self.tool.summarize_call({"layer_name": "Дороги", "values": {"type": 1}, "matched_estimate": 5})
        self.assertIn("5", summary)
        self.assertTrue(self.tool.summarize_call({}).strip())

    def test_no_matches_is_a_prepare_error(self):
        self.layer._features = []
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertIn("nothing to update", str(caught.exception))


class DeleteFeaturesTest(EditTestBase):
    def setUp(self):
        super().setUp()
        self.tool = DeleteFeaturesTool()

    def test_missing_filter_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "filter": "  "})
        self.assertIn("'all'", str(caught.exception))

    def test_the_all_marker_deletes_everything(self):
        result = self.tool.execute({"layer_name": "Дороги", "filter": "all"})
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(self.layer._features, [])

    def test_apply_uses_the_layer_id_bound_during_prepare(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "filter": "all"})
        delete_module.find_layer_by_name = lambda name: (_ for _ in ()).throw(AssertionError("name lookup used"))
        result = self.tool.execute(prepared)
        self.assertEqual(result["deleted"], 2)

    def test_apply_deletes_only_the_feature_ids_bound_during_prepare(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "filter": "all"})
        self.layer._features.append(Feature(3, {"name": "c", "type": "new"}))
        result = self.tool.execute(prepared)
        self.assertEqual(result["deleted"], 2)
        self.assertEqual([feature.id() for feature in self.layer._features], [3])

    def test_missing_prepared_feature_aborts_before_editing(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "filter": "all"})
        self.layer._features = self.layer._features[:1]
        with self.assertRaisesRegex(ValueError, "no longer exist"):
            self.tool.execute(prepared)
        self.assertFalse(self.layer.editing)

    def test_too_many_matches_are_refused(self):
        self.layer._features = [Feature(i, {}) for i in range(delete_module.MAX_DELETE + 1)]
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "filter": "all"})
        self.assertIn(str(delete_module.MAX_DELETE), str(caught.exception))

    def test_failed_commit_rolls_back(self):
        self.layer._commit_ok = False
        with self.assertRaises(ValueError):
            self.tool.execute({"layer_name": "Дороги", "filter": "all"})
        self.assertTrue(self.layer.rolled_back)

    def test_refused_deletion_never_commits_or_reports_success(self):
        with (
            patch.object(self.layer, "deleteFeatures", return_value=False),
            self.assertRaisesRegex(ValueError, "refused to delete"),
        ):
            self.tool.execute({"layer_name": "Дороги", "filter": "all"})
        self.assertTrue(self.layer.rolled_back)
        self.assertEqual(self.layer.commit_calls, 0)
        self.assertEqual(len(self.layer._features), 2)

    def test_deletion_exception_closes_the_owned_edit_session(self):
        with (
            patch.object(self.layer, "deleteFeatures", side_effect=RuntimeError("provider failure")),
            self.assertRaisesRegex(ValueError, "provider failure"),
        ):
            self.tool.execute({"layer_name": "Дороги", "filter": "all"})
        self.assertTrue(self.layer.rolled_back)
        self.assertFalse(self.layer.editing)

    def test_summary_shows_the_count_and_never_raises(self):
        self.assertIn("3", self.tool.summarize_call({"layer_name": "Дороги", "matched_estimate": 3}))
        self.assertTrue(self.tool.summarize_call({}).strip())


class ContractTest(unittest.TestCase):
    def test_both_tools_are_destructive(self):
        from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE

        self.assertEqual(UpdateAttributesTool().safety, SAFETY_DESTRUCTIVE)
        self.assertEqual(DeleteFeaturesTool().safety, SAFETY_DESTRUCTIVE)

    def test_committed_data_source_edits_are_external_to_project_undo(self):
        self.assertTrue(UpdateAttributesTool().external_effect)
        self.assertTrue(DeleteFeaturesTool().external_effect)


if __name__ == "__main__":
    unittest.main()
