import os
import shutil
import tempfile
import unittest

from qgis_ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_WRITE
from qgis_ai_agent.qgis_tools.layout import export_layout as layout_module
from qgis_ai_agent.qgis_tools.layout.export_layout import ExportLayoutTool
from qgis_ai_agent.qgis_tools.processing.run_processing import (
    RunProcessingTool,
    _check_destinations,
    _destination_paths,
    _destination_values,
)
from qgis_ai_agent.qgis_tools.project import export_layer as layer_module
from qgis_ai_agent.qgis_tools.project.export_layer import ExportLayerTool


class _Layer:
    selected_ids = [1]

    @staticmethod
    def name():
        return "roads"

    @staticmethod
    def selectedFeatureCount():
        return 1

    @classmethod
    def selectedFeatureIds(cls):
        return list(cls.selected_ids)

    @staticmethod
    def id():
        return "roads-id"


class _Pages:
    @staticmethod
    def pageCount():
        return 2


class _Layout:
    @staticmethod
    def pageCollection():
        return _Pages()


class OutputSafetyTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.existing_pdf = os.path.join(self.root, "map.pdf")
        self.existing_gpkg = os.path.join(self.root, "roads.gpkg")
        for path in (self.existing_pdf, self.existing_gpkg):
            with open(path, "wb") as handle:
                handle.write(b"existing")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_layout_export_refuses_an_implicit_overwrite(self):
        saved = layout_module.find_layout
        layout_module.find_layout = lambda name: object()
        try:
            with self.assertRaisesRegex(ValueError, "overwrite=true"):
                ExportLayoutTool().prepare({"layout_name": "Sheet", "path": self.existing_pdf})
        finally:
            layout_module.find_layout = saved

    def test_layout_explicit_overwrite_is_destructive(self):
        tool = ExportLayoutTool()
        call = {"layout_name": "Sheet", "path": self.existing_pdf, "overwrite": True}
        self.assertEqual(tool.safety_for(call), SAFETY_DESTRUCTIVE)

    def test_new_layout_export_is_a_regular_write(self):
        path = os.path.join(self.root, "new.pdf")
        self.assertEqual(ExportLayoutTool().safety_for({"path": path}), SAFETY_WRITE)

    def test_explicit_overwrite_is_destructive_even_before_the_target_exists(self):
        path = os.path.join(self.root, "appears-later.pdf")
        self.assertEqual(
            ExportLayoutTool().safety_for({"path": path, "overwrite": True}),
            SAFETY_DESTRUCTIVE,
        )

    def test_layer_export_refuses_an_implicit_overwrite(self):
        saved = layer_module._require_vector
        layer_module._require_vector = lambda name: _Layer()
        try:
            with self.assertRaisesRegex(ValueError, "overwrite=true"):
                ExportLayerTool().prepare({"layer_name": "roads", "path": self.existing_gpkg})
        finally:
            layer_module._require_vector = saved

    def test_layer_export_refuses_to_replace_a_dangling_symlink(self):
        target = os.path.join(self.root, "dangling.geojson")
        try:
            os.symlink(os.path.join(self.root, "missing-target"), target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")
        saved = layer_module._require_vector
        layer_module._require_vector = lambda name: _Layer()
        try:
            with self.assertRaisesRegex(ValueError, "overwrite=true"):
                ExportLayerTool().prepare({"layer_name": "roads", "path": target})
        finally:
            layer_module._require_vector = saved

    def test_shapefile_export_refuses_to_replace_an_existing_sidecar(self):
        target = os.path.join(self.root, "new.shp")
        with open(os.path.join(self.root, "new.dbf"), "wb") as handle:
            handle.write(b"existing attributes")
        saved = layer_module._require_vector
        layer_module._require_vector = lambda name: _Layer()
        try:
            with self.assertRaisesRegex(ValueError, "overwrite=true"):
                ExportLayerTool().prepare({"layer_name": "roads", "path": target})
        finally:
            layer_module._require_vector = saved

    def test_shapefile_export_refuses_to_replace_an_existing_spatial_index(self):
        target = os.path.join(self.root, "indexed.shp")
        with open(os.path.join(self.root, "indexed.qix"), "wb") as handle:
            handle.write(b"existing index")
        saved = layer_module._require_vector
        layer_module._require_vector = lambda name: _Layer()
        try:
            with self.assertRaisesRegex(ValueError, "overwrite=true"):
                ExportLayerTool().prepare({"layer_name": "roads", "path": target})
        finally:
            layer_module._require_vector = saved

    def test_shapefile_export_refuses_to_replace_an_existing_attribute_index(self):
        target = os.path.join(self.root, "attribute-indexed.shp")
        with open(os.path.join(self.root, "attribute-indexed.ind"), "wb") as handle:
            handle.write(b"existing index")
        saved = layer_module._require_vector
        layer_module._require_vector = lambda name: _Layer()
        try:
            with self.assertRaisesRegex(ValueError, "overwrite=true"):
                ExportLayerTool().prepare({"layer_name": "roads", "path": target})
        finally:
            layer_module._require_vector = saved

    def test_prepared_layer_export_is_pinned_to_an_id(self):
        saved = layer_module._require_vector
        layer_module._require_vector = lambda name: _Layer()
        try:
            prepared = ExportLayerTool().prepare(
                {"layer_name": "roads", "path": os.path.join(self.root, "new.geojson")}
            )
        finally:
            layer_module._require_vector = saved
        self.assertEqual(prepared["layer_id"], "roads-id")

    def test_layer_id_is_an_optional_public_export_parameter(self):
        parameters = {item["name"]: item for item in ExportLayerTool.params_schema}
        self.assertIn("layer_id", parameters)
        self.assertFalse(parameters["layer_id"]["required"])

    def test_layer_id_disambiguates_duplicate_names_during_prepare(self):
        saved_id = layer_module.find_layer_by_id
        saved_name = layer_module.find_layer_by_name
        saved_type = layer_module.QgsVectorLayer
        chosen = _Layer()
        layer_module.find_layer_by_id = lambda layer_id: chosen

        def ambiguous_name(name):
            raise AssertionError(f"ambiguous name lookup used for {name}")

        layer_module.find_layer_by_name = ambiguous_name
        layer_module.QgsVectorLayer = _Layer
        try:
            prepared = ExportLayerTool().prepare(
                {
                    "layer_name": "roads",
                    "layer_id": "roads-id",
                    "path": os.path.join(self.root, "by-id.geojson"),
                }
            )
        finally:
            layer_module.find_layer_by_id = saved_id
            layer_module.find_layer_by_name = saved_name
            layer_module.QgsVectorLayer = saved_type
        self.assertEqual(prepared["layer_id"], "roads-id")

    def test_layer_id_target_must_still_be_a_vector(self):
        class Raster:
            @staticmethod
            def name():
                return "roads"

        saved_id = layer_module.find_layer_by_id
        saved_type = layer_module.QgsVectorLayer
        layer_module.find_layer_by_id = lambda layer_id: Raster()
        layer_module.QgsVectorLayer = _Layer
        try:
            with self.assertRaisesRegex(ValueError, "not a vector layer"):
                ExportLayerTool().prepare(
                    {
                        "layer_name": "roads",
                        "layer_id": "raster-id",
                        "path": os.path.join(self.root, "raster.geojson"),
                    }
                )
        finally:
            layer_module.find_layer_by_id = saved_id
            layer_module.QgsVectorLayer = saved_type

    def test_selected_export_pins_exact_feature_ids(self):
        saved = layer_module._require_vector
        layer_module._require_vector = lambda name: _Layer()
        try:
            prepared = ExportLayerTool().prepare(
                {
                    "layer_name": "roads",
                    "path": os.path.join(self.root, "selection.geojson"),
                    "selected_only": True,
                }
            )
        finally:
            layer_module._require_vector = saved
        self.assertEqual(prepared["_selected_feature_ids"], [1])

    def test_changed_selection_is_rejected_before_export(self):
        with self.assertRaisesRegex(ValueError, "selected features changed"):
            layer_module._validate_selection(
                _Layer(),
                {"selected_only": True, "_selected_feature_ids": [2]},
            )

    def test_geopackage_export_refuses_to_remove_an_existing_journal(self):
        target = os.path.join(self.root, "new.gpkg")
        with open(target + "-journal", "wb") as handle:
            handle.write(b"existing journal")
        saved = layer_module._require_vector
        layer_module._require_vector = lambda name: _Layer()
        try:
            with self.assertRaisesRegex(ValueError, "overwrite=true"):
                ExportLayerTool().prepare({"layer_name": "roads", "path": target})
        finally:
            layer_module._require_vector = saved

    def test_multipage_png_refuses_to_replace_a_numbered_page(self):
        target = os.path.join(self.root, "map.png")
        with open(os.path.join(self.root, "map_2.png"), "wb") as handle:
            handle.write(b"existing second page")
        saved = layout_module.find_layout
        layout_module.find_layout = lambda name: _Layout()
        try:
            with self.assertRaisesRegex(ValueError, "overwrite=true"):
                ExportLayoutTool().prepare({"layout_name": "Sheet", "path": target})
        finally:
            layout_module.find_layout = saved

    def test_processing_only_treats_destinations_as_outputs(self):
        parameters = {
            "INPUT": self.existing_gpkg,
            "OUTPUT": self.existing_pdf,
            "SECONDARY_DESTINATION": "TEMPORARY_OUTPUT",
        }
        self.assertEqual(_destination_paths(parameters), [self.existing_pdf])

    def test_processing_refuses_an_implicit_overwrite(self):
        with self.assertRaisesRegex(ValueError, "overwrite=true"):
            _check_destinations({"OUTPUT": self.existing_pdf}, overwrite=False)

    def test_processing_uses_typed_destination_names_not_only_output_spelling(self):
        self.assertEqual(
            _destination_paths({"FOLDER": self.root}, ["FOLDER"]),
            [self.root],
        )
        with self.assertRaisesRegex(ValueError, "overwrite=true"):
            _check_destinations({"FOLDER": self.root}, False, ["FOLDER"])

    def test_database_destination_is_external_but_not_a_filesystem_path(self):
        parameters = {"OUTPUT": "postgres:dbname=gis table=roads"}
        self.assertEqual(_destination_values(parameters), [parameters["OUTPUT"]])
        self.assertEqual(_destination_paths(parameters), [])
        self.assertTrue(RunProcessingTool().has_external_effect({"parameters": parameters}))

    def test_database_sql_algorithm_always_gets_destructive_confirmation(self):
        call = {"algorithm_id": "native:postgisexecutesql", "parameters": {"SQL": "DELETE FROM roads"}}
        tool = RunProcessingTool()
        self.assertTrue(tool.has_external_effect(call))
        self.assertEqual(tool.safety_for(call), SAFETY_DESTRUCTIVE)

    def test_spatialite_import_without_destination_definition_is_destructive(self):
        call = {"algorithm_id": "native:importintospatialite", "parameters": {"TABLENAME": "roads"}}
        tool = RunProcessingTool()
        self.assertTrue(tool.has_external_effect(call))
        self.assertEqual(tool.safety_for(call), SAFETY_DESTRUCTIVE)

    def test_processing_explicit_overwrite_is_destructive(self):
        call = {"parameters": {"OUTPUT": self.existing_pdf}, "overwrite_outputs": True}
        self.assertEqual(RunProcessingTool().safety_for(call), SAFETY_DESTRUCTIVE)


if __name__ == "__main__":
    unittest.main()
