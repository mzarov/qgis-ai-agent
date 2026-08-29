import os
import shutil
import tempfile
import unittest

from qgis_ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_WRITE
from qgis_ai_agent.qgis_tools.project import (
    add_layer,
    configure_layer,
    configure_project,
    remove_layer,
    save_project,
    tree,
    zoom_to_layer,
)
from tests.fake_layers import Field, Layer


class Node:
    def __init__(self, layer, parent=None):
        self.layer = layer
        self._parent = parent
        self.visible = True

    def parent(self):
        return self._parent

    def setItemVisibilityChecked(self, value):
        self.visible = value

    def itemVisibilityChecked(self):
        return self.visible

    def clone(self):
        twin = Node(self.layer, self._parent)
        twin.visible = self.visible
        return twin


class Group:
    def __init__(self, name="", parent=None):
        self._name = name
        self._parent = parent
        self._children = []

    def name(self):
        return self._name

    def parent(self):
        return self._parent

    def children(self):
        return list(self._children)

    def addGroup(self, name):
        made = Group(name, self)
        self._children.append(made)
        return made

    def findGroup(self, name):
        for child in self._children:
            if isinstance(child, Group) and child.name() == name:
                return child
            if isinstance(child, Group):
                found = child.findGroup(name)
                if found is not None:
                    return found
        return None

    def findLayer(self, identifier):
        for child in self._children:
            if isinstance(child, Node) and child.layer.id() == identifier:
                return child
            if isinstance(child, Group):
                found = child.findLayer(identifier)
                if found is not None:
                    return found
        return None

    def addLayer(self, layer):
        node = Node(layer, self)
        self._children.append(node)
        return node

    def insertChildNode(self, index, node):
        node._parent = self
        self._children.insert(index, node)

    def removeChildNode(self, node):
        if node in self._children:
            self._children.remove(node)


class Project:
    def __init__(self, layers=(), path=""):
        self.root = Group()
        self._layers = {}
        self._path = path
        self.title_set = None
        self.crs_set = None
        self.written = None
        self.write_ok = True
        for layer in layers:
            self._layers[layer.id()] = layer
            self.root.addLayer(layer)

    def layerTreeRoot(self):
        return self.root

    def mapLayers(self):
        return dict(self._layers)

    def addMapLayer(self, layer, to_tree=True):
        self._layers[layer.id()] = layer
        if to_tree:
            self.root.addLayer(layer)
        return layer

    def removeMapLayer(self, identifier):
        self._layers.pop(identifier, None)

    def fileName(self):
        return self._path

    def setTitle(self, value):
        self.title_set = value

    def setCrs(self, value):
        self.crs_set = value

    def crs(self):
        return type("Crs", (), {"authid": staticmethod(lambda: "EPSG:3857")})()

    def write(self, path):
        self.written = path
        return self.write_ok


class ProjectCase(unittest.TestCase):
    modules = (add_layer, configure_project, remove_layer, save_project)

    def setUp(self):
        self.layer = Layer(name="Дороги", fields=(Field("name"),))
        self.project = Project([self.layer])
        self._saved = (tree.project, tree.find_layer_by_name)
        tree.project = lambda: self.project
        tree.find_layer_by_name = self._find
        self._modules = {module: module.project for module in self.modules}
        for module in self.modules:
            module.project = lambda: self.project

    def tearDown(self):
        for module, value in self._modules.items():
            module.project = value
        tree.project, tree.find_layer_by_name = self._saved

    def _find(self, name):
        for layer in self.project.mapLayers().values():
            if layer.name() == name:
                return layer
        raise ValueError(f"Слоя «{name}» нет в проекте.")


class AddLayerTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.tool = add_layer.AddLayerTool()
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "города.geojson")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{}")
        self._builders = (add_layer.QgsVectorLayer, add_layer.QgsRasterLayer)
        add_layer.QgsVectorLayer = lambda source, name, provider: _Made(name, True)
        add_layer.QgsRasterLayer = lambda source, name: _Made(name, True, kind="raster")

    def tearDown(self):
        add_layer.QgsVectorLayer, add_layer.QgsRasterLayer = self._builders
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def test_name_defaults_to_the_file_stem(self):
        prepared = self.tool.prepare({"source": self.path})
        self.assertEqual(prepared["name"], "города")

    def test_kind_comes_from_the_extension(self):
        self.assertEqual(self.tool.prepare({"source": self.path})["kind"], "vector")
        raster = os.path.join(self.folder, "подложка.tif")
        open(raster, "w").close()
        self.assertEqual(self.tool.prepare({"source": raster})["kind"], "raster")

    def test_missing_file_is_rejected_before_queueing(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"source": "/нет/такого.shp"})
        self.assertIn("no file", str(caught.exception))

    def test_duplicate_name_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"source": self.path, "name": "Дороги"})
        self.assertIn("is already in the project", str(caught.exception))

    def test_layer_lands_in_the_project(self):
        result = self.tool.execute({"source": self.path})
        self.assertEqual(result["name"], "города")
        self.assertIn("города", [item.name() for item in self.project.mapLayers().values()])

    def test_group_is_created_on_the_way(self):
        self.tool.execute({"source": self.path, "group": "Фон"})
        self.assertIsNotNone(self.project.root.findGroup("Фон"))

    def test_broken_source_reports_the_reason(self):
        add_layer.QgsVectorLayer = lambda source, name, provider: _Made(name, False)
        with self.assertRaises(ValueError) as caught:
            self.tool.execute({"source": self.path})
        self.assertIn("could not open", str(caught.exception))

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"source": self.path, "kind": "облако"})

    def test_summary_names_the_layer(self):
        self.assertIn("города", self.tool.summarize_call({"source": self.path}))

    def test_summary_survives_empty_params(self):
        self.assertTrue(self.tool.summarize_call({}).strip())


class RemoveLayerTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.tool = remove_layer.RemoveLayerTool()

    def test_layer_leaves_the_project(self):
        self.tool.execute({"layer_name": "Дороги"})
        self.assertEqual(self.project.mapLayers(), {})

    def test_result_says_the_file_survives(self):
        self.assertIn("on disk", self.tool.execute({"layer_name": "Дороги"})["note"])

    def test_missing_layer_is_rejected_before_queueing(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_name": "Нет такого"})


class ConfigureLayerTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.tool = configure_layer.ConfigureLayerTool()

    def test_visibility_is_applied(self):
        result = self.tool.execute({"layer_name": "Дороги", "properties": {"visible": False}})
        self.assertFalse(result["visible"])

    def test_rename_is_applied(self):
        self.tool.execute({"layer_name": "Дороги", "properties": {"name": "Дороги города"}})
        self.assertEqual(self.layer.name(), "Дороги города")

    def test_rename_to_an_existing_name_is_rejected(self):
        self.project.addMapLayer(Layer(name="Реки"))
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"name": "Реки"}})
        self.assertIn("is already in the project", str(caught.exception))

    def test_group_move_creates_the_group(self):
        result = self.tool.execute({"layer_name": "Дороги", "properties": {"group": "Транспорт"}})
        self.assertEqual(result["group"], "Транспорт")

    def test_empty_group_returns_to_the_root(self):
        self.tool.execute({"layer_name": "Дороги", "properties": {"group": "Транспорт"}})
        result = self.tool.execute({"layer_name": "Дороги", "properties": {"group": ""}})
        self.assertEqual(result["group"], tree.ROOT_GROUP)

    def test_position_zero_puts_the_layer_on_top(self):
        self.project.addMapLayer(Layer(name="Реки"))
        self.tool.execute({"layer_name": "Дороги", "properties": {"position": 0}})
        first = self.project.root.children()[0]
        self.assertEqual(first.layer.name(), "Дороги")

    def test_empty_bag_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {}})
        self.assertIn("visible", str(caught.exception))

    def test_unknown_property_suggests_a_close_one(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"visable": True}})
        self.assertIn("visible", str(caught.exception))

    def test_summary_lists_what_changes(self):
        summary = self.tool.summarize_call({"layer_name": "Дороги", "properties": {"visible": False}})
        self.assertIn("visible=False", summary)


class ConfigureProjectTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.tool = configure_project.ConfigureProjectTool()
        self._crs = configure_project.QgsCoordinateReferenceSystem
        configure_project.QgsCoordinateReferenceSystem = _Crs

    def tearDown(self):
        configure_project.QgsCoordinateReferenceSystem = self._crs
        super().tearDown()

    def test_title_is_applied(self):
        self.tool.execute({"properties": {"title": "Транспорт"}})
        self.assertEqual(self.project.title_set, "Транспорт")

    def test_crs_is_applied(self):
        self.tool.execute({"properties": {"crs": "EPSG:3857"}})
        self.assertIsNotNone(self.project.crs_set)

    def test_broken_crs_is_rejected_before_queueing(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"properties": {"crs": "меркатор"}})
        self.assertIn("EPSG", str(caught.exception))

    def test_empty_bag_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"properties": {}})


class SaveProjectTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.tool = save_project.SaveProjectTool()

    def test_unsaved_project_demands_a_path(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({})
        self.assertIn("path", str(caught.exception))

    def test_known_path_is_reused(self):
        self.project._path = "/data/город.qgz"
        self.tool.execute({})
        self.assertEqual(self.project.written, "/data/город.qgz")

    def test_suffix_is_added(self):
        self.assertEqual(self.tool.prepare({"path": "/data/город"})["path"], "/data/город.qgz")

    def test_existing_suffix_is_kept(self):
        self.assertEqual(self.tool.prepare({"path": "/data/город.qgs"})["path"], "/data/город.qgs")

    def test_write_failure_is_reported(self):
        self.project.write_ok = False
        with self.assertRaises(ValueError) as caught:
            self.tool.execute({"path": "/data/город"})
        self.assertIn("could not write", str(caught.exception))

    def test_save_as_refuses_to_replace_another_project_without_opt_in(self):
        self.project._path = "/data/current.qgz"
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "existing.qgz")
            open(target, "w").close()
            with self.assertRaises(ValueError) as caught:
                self.tool.prepare({"path": target})
        self.assertIn("overwrite=true", str(caught.exception))

    def test_explicit_overwrite_of_another_project_is_destructive(self):
        self.project._path = "/data/current.qgz"
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "existing.qgz")
            open(target, "w").close()
            prepared = self.tool.prepare({"path": target, "overwrite": True})
            self.assertEqual(self.tool.safety_for(prepared), SAFETY_DESTRUCTIVE)

    def test_target_created_after_planning_is_not_silently_replaced(self):
        self.project._path = "/data/current.qgz"
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "appears-later.qgz")
            prepared = self.tool.prepare({"path": target})
            open(target, "w").close()
            with self.assertRaises(ValueError):
                self.tool.execute(prepared)

    def test_saving_the_current_project_path_remains_an_ordinary_write(self):
        with tempfile.TemporaryDirectory() as folder:
            current = os.path.join(folder, "current.qgz")
            open(current, "w").close()
            self.project._path = current
            prepared = self.tool.prepare({"path": current})
            self.assertEqual(self.tool.safety_for(prepared), SAFETY_WRITE)

    def test_save_project_is_an_external_effect(self):
        self.assertTrue(self.tool.external_effect)

    def test_qgs_save_as_refuses_to_replace_an_existing_attachment_archive(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        target = os.path.join(folder, "city.qgs")
        with open(os.path.join(folder, "city_attachments.zip"), "wb") as handle:
            handle.write(b"existing attachments")
        with self.assertRaisesRegex(ValueError, "overwrite=true"):
            self.tool.prepare({"path": target})

    def test_current_qgs_sidecars_remain_exempt_from_save_as_collision_guard(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        target = os.path.join(folder, "city.qgs")
        for path in (target, os.path.join(folder, "city.qgd"), os.path.join(folder, "city_attachments.zip")):
            with open(path, "wb") as handle:
                handle.write(b"current project")
        self.project._path = target
        self.assertEqual(self.tool.prepare({"path": target})["path"], target)


class ZoomToLayerTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.tool = zoom_to_layer.ZoomToLayerTool()

    def test_zoom_is_read_only(self):
        self.assertTrue(self.tool.is_read_only)

    def test_missing_layer_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tool.execute({"layer_name": "Нет такого"})

    def test_headless_canvas_is_reported_not_swallowed(self):
        saved = (zoom_to_layer.safe_extent, zoom_to_layer._apply_extent)
        zoom_to_layer.safe_extent = lambda layer: object()
        zoom_to_layer._apply_extent = lambda layer, extent: False
        try:
            with self.assertRaises(ValueError) as caught:
                self.tool.execute({"layer_name": "Дороги"})
            self.assertIn("map is not available", str(caught.exception))
        finally:
            zoom_to_layer.safe_extent, zoom_to_layer._apply_extent = saved

    def test_empty_layer_without_extent_is_reported(self):
        saved = zoom_to_layer.safe_extent
        zoom_to_layer.safe_extent = lambda layer: None
        try:
            with self.assertRaises(ValueError) as caught:
                self.tool.execute({"layer_name": "Дороги"})
            self.assertIn("no extent", str(caught.exception))
        finally:
            zoom_to_layer.safe_extent = saved


class _Made:
    def __init__(self, name, valid, kind="vector"):
        self._name = name
        self._valid = valid
        self.kind = kind

    def name(self):
        return self._name

    def id(self):
        return f"{self._name}_id"

    def isValid(self):
        return self._valid

    def error(self):
        return type("Error", (), {"summary": staticmethod(lambda: "файл пуст")})()


class _Crs:
    def __init__(self, text):
        self._text = text

    def isValid(self):
        return self._text.upper().startswith("EPSG:")

    def authid(self):
        return self._text


if __name__ == "__main__":
    unittest.main()
