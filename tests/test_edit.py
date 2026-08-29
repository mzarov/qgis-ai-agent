import unittest

from qgis.core import QgsVectorLayer

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

    def name(self):
        return "Дороги"

    def fields(self):
        return self._fields

    def getFeatures(self, request=None):
        return iter(list(self._features))

    def startEditing(self):
        self.editing = True
        return True

    def changeAttributeValue(self, fid, index, value):
        self.changes.append((fid, index, value))
        for feature in self._features:
            if feature.id() == fid:
                feature.attributes[self._fields.names()[index]] = value

    def deleteFeatures(self, ids):
        wanted = set(ids)
        self._features = [feature for feature in self._features if feature.id() not in wanted]

    def commitChanges(self):
        return self._commit_ok

    def commitErrors(self):
        return ["disk full"]

    def rollBack(self):
        self.rolled_back = True


class EditTestBase(unittest.TestCase):
    def setUp(self):
        self.layer = EditableLayer(
            ["name", "type"], [(1, {"name": "a", "type": "old"}), (2, {"name": "b", "type": "old"})]
        )
        self._saved = []
        for module in (update_module, delete_module):
            self._saved.append((module, module.find_layer_by_name, module.build_request))
            module.find_layer_by_name = lambda name: self.layer
            module.build_request = lambda text, layer=None: None
        update_module.build_context = lambda layer: None

    def tearDown(self):
        for module, finder, builder in self._saved:
            module.find_layer_by_name = finder
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

    def test_execute_changes_every_matching_feature(self):
        result = self.tool.execute({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertEqual(result["updated"], 2)
        self.assertTrue(all(f.attributes["type"] == "new" for f in self.layer._features))

    def test_failed_commit_rolls_back_and_reports(self):
        self.layer._commit_ok = False
        with self.assertRaises(ValueError) as caught:
            self.tool.execute({"layer_name": "Дороги", "values": {"type": "new"}})
        self.assertTrue(self.layer.rolled_back)
        self.assertIn("disk full", str(caught.exception))
        self.assertIn("nothing changed", str(caught.exception))

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

    def test_summary_shows_the_count_and_never_raises(self):
        self.assertIn("3", self.tool.summarize_call({"layer_name": "Дороги", "matched_estimate": 3}))
        self.assertTrue(self.tool.summarize_call({}).strip())


class ContractTest(unittest.TestCase):
    def test_both_tools_are_destructive(self):
        from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE

        self.assertEqual(UpdateAttributesTool().safety, SAFETY_DESTRUCTIVE)
        self.assertEqual(DeleteFeaturesTool().safety, SAFETY_DESTRUCTIVE)


if __name__ == "__main__":
    unittest.main()
