import unittest

from ai_agent.qgis_tools.fields import manage_fields as fields_module
from ai_agent.qgis_tools.fields import schema
from ai_agent.qgis_tools.fields.manage_fields import AddFieldTool, DeleteFieldTool, RenameFieldTool
from tests.test_coverage_tools import Fields, VectorLayer


class OriginFields(Fields):
    def __init__(self, names, virtual=()):
        super().__init__(names)
        self._virtual = set(virtual)

    def fieldOrigin(self, index):
        origin = schema.Qgis.FieldOrigin
        return origin.Expression if self._names[index] in self._virtual else origin.Provider


class StoredLayer(VectorLayer):
    def __init__(self, names=("name", "type"), virtual=(), storage="GPKG", stores=None):
        super().__init__(names)
        self._fields = OriginFields(names, virtual)
        self._storage = storage
        self._stores = stores

    def storageType(self):
        return self._storage

    def startEditing(self):
        if self._storage == "read-only":
            return False
        return super().startEditing()

    def addAttribute(self, field):
        self._fields._names.append(self._stores or "added")
        return super().addAttribute(field)

    def renameAttribute(self, index, new_name):
        self._fields._names[index] = self._stores or new_name
        return super().renameAttribute(index, new_name)


class FieldsCase(unittest.TestCase):
    layer: StoredLayer

    def setUp(self):
        self.saved = (fields_module.require_vector, fields_module.compile_expression)
        fields_module.require_vector = lambda name: self.layer
        fields_module.compile_expression = lambda text, label, layer=None: None

    def tearDown(self):
        fields_module.require_vector, fields_module.compile_expression = self.saved


class ShapefileNameTest(FieldsCase):
    def setUp(self):
        super().setUp()
        self.layer = StoredLayer(storage=schema.SHAPEFILE_STORAGE)

    def test_a_name_the_format_would_truncate_is_refused_before_apply(self):
        for tool, arguments in (
            (AddFieldTool(), {"name": "population_2020", "type": "integer"}),
            (AddFieldTool(), {"name": "население", "type": "text"}),
            (RenameFieldTool(), {"name": "name", "new_name": "settlement_name"}),
        ):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValueError, "Shapefile field name"):
                tool.prepare({"layer_name": "towns", **arguments})

    def test_a_short_name_and_a_virtual_field_pass(self):
        AddFieldTool().prepare({"layer_name": "towns", "name": "population", "type": "integer"})
        AddFieldTool().prepare({"layer_name": "towns", "name": "population_density", "expression": "1", "type": "text"})

    def test_other_formats_keep_long_names(self):
        self.layer = StoredLayer()
        AddFieldTool().prepare({"layer_name": "towns", "name": "population_2020", "type": "integer"})


class StoredNameTest(FieldsCase):
    def test_the_result_names_the_field_the_layer_has_now(self):
        self.layer = StoredLayer(stores="populat")
        added = AddFieldTool().execute({"layer_name": "towns", "name": "population", "type": "integer"})
        self.assertEqual(added["field"], "populat")
        renamed = RenameFieldTool().execute({"layer_name": "towns", "name": "name", "new_name": "settlement"})
        self.assertEqual(renamed["to"], "populat")


class VirtualFieldTest(FieldsCase):
    def setUp(self):
        super().setUp()
        self.layer = StoredLayer(("id", "double"), virtual=("double",), storage="read-only")

    def test_a_virtual_field_is_renamed_and_deleted_without_an_edit_session(self):
        RenameFieldTool().execute({"layer_name": "stats", "name": "double", "new_name": "twice"})
        self.assertEqual(self.layer.renamed, [(1, "twice")])
        self.layer._fields = OriginFields(("id", "twice"), virtual=("twice",))
        DeleteFieldTool().execute({"layer_name": "stats", "name": "twice"})
        self.assertEqual(self.layer.deleted, [1])
        self.assertEqual(self.layer.commit_calls, 0)

    def test_a_stored_field_of_a_read_only_layer_is_still_refused(self):
        with self.assertRaisesRegex(ValueError, "cannot be switched into editing mode"):
            RenameFieldTool().execute({"layer_name": "stats", "name": "id", "new_name": "code"})

    def test_only_a_stored_field_is_an_external_change(self):
        self.assertFalse(RenameFieldTool().has_external_effect({"layer_name": "stats", "name": "double"}))
        self.assertFalse(DeleteFieldTool().has_external_effect({"layer_name": "stats", "name": "double"}))
        self.assertTrue(DeleteFieldTool().has_external_effect({"layer_name": "stats", "name": "id"}))
        self.assertTrue(DeleteFieldTool().has_external_effect({}))


class FieldTypeTest(unittest.TestCase):
    def test_a_date_leaves_its_length_to_the_format(self):
        self.assertEqual(schema.FIELD_TYPES["date"][1:], (0, 0))


if __name__ == "__main__":
    unittest.main()
