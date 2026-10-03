import os
import tempfile
import unittest
from unittest import mock

from qgis.core import QgsVectorLayer

from ai_agent.qgis_tools.common import layers as layers_module
from ai_agent.qgis_tools.registry import get_tools_for_skills
from ai_agent.qgis_tools.tables import join_table as join_module
from ai_agent.qgis_tools.tables import list_joins as list_module
from ai_agent.qgis_tools.tables import source as source_module
from ai_agent.qgis_tools.tables.join_table import JoinTableTool
from ai_agent.qgis_tools.tables.list_joins import ListJoinsTool
from ai_agent.qgis_tools.tables.remove_join import RemoveJoinTool


class Field:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class Fields:
    def __init__(self, names):
        self._names = list(names)

    def names(self):
        return list(self._names)

    def indexFromName(self, name):
        return self._names.index(name) if name in self._names else -1

    def __iter__(self):
        return iter([Field(name) for name in self._names])


class Join:
    def __init__(self, table, layer_field, table_field, prefix="", subset=None):
        self.table, self.layer_field, self.table_field = table, layer_field, table_field
        self.prefix, self.subset = prefix, subset

    def joinLayer(self):
        return self.table

    def joinLayerId(self):
        return self.table.id() if self.table is not None else "gone_id"

    def targetFieldName(self):
        return self.layer_field

    def joinFieldName(self):
        return self.table_field

    def joinFieldNamesSubset(self):
        return self.subset

    def prefixedFieldName(self, field):
        return (self.prefix if self.prefix else f"{self.table.name()}_") + field.name()


class Layer(QgsVectorLayer):
    def __init__(self, name, columns, provider="ogr", source="", layer_id=""):
        self._name, self._provider, self._source = name, provider, source
        self._id = layer_id or f"{name}_id"
        self._fields = Fields(columns)
        self.values = {column: [] for column in columns}
        self.joins = []
        self.added_infos = []
        self.add_ok = True

    def name(self):
        return self._name

    def id(self):
        return self._id

    def fields(self):
        return self._fields

    def providerType(self):
        return self._provider

    def source(self):
        return self._source

    def uniqueValues(self, index):
        return set(self.values[self._fields.names()[index]])

    def vectorJoins(self):
        return list(self.joins)

    def addJoin(self, info):
        self.added_infos.append(info)
        return self.add_ok

    def removeJoin(self, identifier):
        before = len(self.joins)
        self.joins = [join for join in self.joins if join.joinLayerId() != identifier]
        return len(self.joins) < before


class Project:
    def __init__(self, layers):
        self.layers = {layer.id(): layer for layer in layers}
        self.added, self.removed = [], []

    def mapLayers(self):
        return dict(self.layers)

    def mapLayersByName(self, name):
        return [layer for layer in self.layers.values() if layer.name() == name]

    def addMapLayer(self, layer, add_to_tree=True):
        self.added.append(layer)
        self.layers[layer.id()] = layer

    def removeMapLayer(self, identifier):
        self.removed.append(identifier)
        self.layers.pop(identifier, None)


class JoinCase(unittest.TestCase):
    def setUp(self):
        self.districts = Layer("districts", ["code", "name"])
        self.districts.values = {"code": ["001", "002", "003"], "name": ["A", "B", "C"]}
        self.population = Layer("population", ["code", "pop", "name"], provider="delimitedtext")
        self.population.values = {"code": ["001", "002"], "pop": [10, 20], "name": ["A", "B"]}
        self.project = Project([self.districts, self.population])
        holder = type("Holder", (), {"instance": staticmethod(lambda: self.project)})
        for module in (layers_module, source_module, join_module, list_module):
            patcher = mock.patch.object(module, "QgsProject", holder)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def csv(self, name, text):
        path = os.path.join(self.folder.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


class JoinTableTest(JoinCase):
    def setUp(self):
        super().setUp()
        self.tool = JoinTableTool()

    def call(self, **extra):
        params = {"layer_name": "districts", "layer_field": "code", "table": "population", "table_field": "code"}
        params.update(extra)
        return params

    def test_prepare_binds_the_layer_and_fills_the_prefix(self):
        prepared = self.tool.prepare(self.call(fields=["pop"]))
        self.assertEqual(prepared["layer_id"], "districts_id")
        self.assertEqual(prepared["prefix"], "population_")
        self.assertEqual(prepared["fields"], ["pop"])
        self.assertEqual(self.tool.prepare(self.call(prefix="", fields=["pop"]))["prefix"], "")

    def test_the_table_is_pinned_by_id(self):
        prepared = self.tool.prepare(self.call(fields=["pop"]))
        self.assertEqual(prepared["table_id"], "population_id")
        with self.assertRaisesRegex(ValueError, "identify different layers"):
            self.tool.execute({**prepared, "table_id": "districts_id"})

    def test_no_shared_key_is_refused_with_the_reason(self):
        self.population.values["code"] = [1, 2]
        with self.assertRaisesRegex(ValueError, "No value of 'districts'.code matches.*leading zeros.*to_int"):
            self.tool.prepare(self.call())

    def test_unknown_fields_and_clashes_are_refused(self):
        with self.assertRaisesRegex(ValueError, "no field 'kod'.*Available fields: code, name"):
            self.tool.prepare(self.call(layer_field="kod"))
        with self.assertRaisesRegex(ValueError, "no field popul.*Available fields: code, pop, name"):
            self.tool.prepare(self.call(fields=["popul"]))
        with self.assertRaisesRegex(ValueError, "repeat names.*name"):
            self.tool.prepare(self.call(prefix="", fields=["name"]))
        with self.assertRaisesRegex(ValueError, "joined to itself"):
            self.tool.prepare(self.call(table="districts"))

    def test_a_second_join_of_the_same_table_is_refused(self):
        self.districts.joins = [Join(self.population, "code", "code")]
        with self.assertRaisesRegex(ValueError, "already joined.*remove_join"):
            self.tool.prepare(self.call())

    def test_execute_joins_and_reports_the_partial_match(self):
        result = self.tool.execute(self.call(prefix="p_", fields=["pop"]))
        self.assertEqual(len(self.districts.added_infos), 1)
        self.assertEqual(result["joined_fields"], ["p_pop"])
        self.assertEqual(result["match"]["matched_keys"], 2)
        self.assertEqual(result["match"]["unmatched_samples"], ["003"])
        self.assertIn("NULL", result["note"])

    def test_a_refused_join_is_an_error(self):
        self.districts.add_ok = False
        with self.assertRaisesRegex(ValueError, "refused to join"):
            self.tool.execute(self.call())

    def test_a_csv_path_is_read_for_the_check_and_loaded_on_execute(self):
        path = self.csv("stats.csv", "kod;households\n001;5\n002;7\n")
        prepared = self.tool.prepare(self.call(table=path, table_field="kod"))
        self.assertEqual(prepared["prefix"], "stats_")
        with self.assertRaisesRegex(ValueError, "no column 'code'.*Available columns: kod, households"):
            self.tool.prepare(self.call(table=path))
        loaded = Layer("stats", ["kod", "households"], provider="delimitedtext")
        loaded.values = {"kod": ["001", "002"], "households": [5, 7]}
        with mock.patch.object(join_module, "open_delimited", return_value=loaded) as opened:
            result = self.tool.execute(prepared)
        self.assertEqual(opened.call_args.args[1], "stats")
        self.assertEqual(result["loaded_table"], "stats")
        self.assertIn(loaded, self.project.added)
        self.assertEqual(result["match"]["matched_keys"], 2)

    def test_a_failed_join_unloads_the_table_it_loaded(self):
        path = self.csv("stats.csv", "kod,households\n001,5\n")
        loaded = Layer("stats", ["kod", "households"], provider="delimitedtext")
        self.districts.add_ok = False
        with (
            mock.patch.object(join_module, "open_delimited", return_value=loaded),
            self.assertRaisesRegex(ValueError, "refused"),
        ):
            self.tool.execute(self.call(table=path, table_field="kod"))
        self.assertEqual(self.project.removed, ["stats_id"])

    def test_a_csv_already_in_the_project_is_reused(self):
        path = self.csv("population.csv", "code,pop\n001,1\n")
        self.population._source = f"file://{path}?type=csv&delimiter=,"
        with mock.patch.object(source_module, "QUrl") as url:
            url.return_value.toLocalFile.return_value = path
            prepared = self.tool.prepare(self.call(table=path))
        self.assertEqual(prepared["prefix"], "population_")

    def test_the_remote_side_is_not_counted(self):
        self.districts._provider = "postgres"
        self.population.values["code"] = [9]
        result = self.tool.execute(self.call())
        self.assertNotIn("match", result)
        self.assertIn("list_joins", result["note"])


class ListAndRemoveJoinsTest(JoinCase):
    def setUp(self):
        super().setUp()
        self.districts.joins = [Join(self.population, "code", "code", subset=["pop"])]

    def test_list_reports_fields_and_matches(self):
        result = ListJoinsTool().execute({"layer_name": "districts"})
        join = result["layers"][0]["joins"][0]
        self.assertEqual(join["table"], "population")
        self.assertEqual(join["joined_fields"], ["population_pop"])
        self.assertEqual(join["match"]["matched_keys"], 2)
        everything = ListJoinsTool().execute({})
        self.assertEqual([entry["layer"] for entry in everything["layers"]], ["districts"])

    def test_a_join_whose_table_is_gone(self):
        self.districts.joins = [Join(None, "code", "code")]
        join = ListJoinsTool().execute({"layer_name": "districts"})["layers"][0]["joins"][0]
        self.assertEqual(join["table"], "gone_id")
        self.assertIn("no longer", join["note"])

    def test_namesakes_need_the_pinned_id(self):
        twin = Layer("population", ["code", "pop"], layer_id="population_2")
        self.project.layers[twin.id()] = twin
        self.districts.joins.append(Join(twin, "code", "code", prefix="b_"))
        tool = RemoveJoinTool()
        with self.assertRaisesRegex(ValueError, "Several tables named 'population'.*population_id.*population_2"):
            tool.prepare({"layer_name": "districts", "table": "population"})
        prepared = tool.prepare({"layer_name": "districts", "table": "population", "table_id": "population_2"})
        self.assertEqual(tool.execute(prepared)["removed_fields"], ["b_pop"])
        self.assertEqual([join.joinLayerId() for join in self.districts.joins], ["population_id"])

    def test_remove(self):
        tool = RemoveJoinTool()
        with self.assertRaisesRegex(ValueError, "no join with 'census'. Joined tables: 'population' \\[id="):
            tool.prepare({"layer_name": "districts", "table": "census"})
        prepared = tool.prepare({"layer_name": "districts", "table": "population"})
        self.assertEqual((prepared["layer_id"], prepared["table_id"]), ("districts_id", "population_id"))
        result = tool.execute(prepared)
        self.assertEqual(result["removed_fields"], ["population_pop"])
        self.assertEqual(self.districts.joins, [])


class SummariesTest(unittest.TestCase):
    def test_summaries_survive_malformed_arguments(self):
        odd = [{}, {"path": 5, "layer_name": None, "table": ["x"], "x_field": 1, "y_field": {}}]
        for tool in get_tools_for_skills(["tables"]):
            for params in odd:
                self.assertTrue(tool.summarize_call(params).strip(), tool.name)

    def test_summaries_repeat_the_arguments(self):
        tool = JoinTableTool()
        text = tool.summarize_call(
            {"layer_name": "districts", "layer_field": "code", "table": "/d/pop.csv", "table_field": "kod"}
        )
        for value in ("districts", "code", "/d/pop.csv", "kod"):
            self.assertIn(value, text)


if __name__ == "__main__":
    unittest.main()
