import json
import unittest
from unittest import mock

from qgis.core import QgsVectorLayer

from ai_agent.core.agent.batch import _model_line
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.registry import get_tool_by_name, summarize_tool_call, summarize_tool_result
from ai_agent.qgis_tools.sql import create_sql_layer as create_module
from ai_agent.qgis_tools.sql import virtual as virtual_module
from ai_agent.qgis_tools.sql.query_sql import MAX_ROWS, MAX_TEXT_CHARS, cell
from ai_agent.qgis_tools.sql.statement import SUMMARY_CHARS, checked_sql, identifiers, short_sql, tokenize
from ai_agent.qgis_tools.sql.virtual import SOURCES_KEY, query_error

JOIN = 'SELECT d.name, count(s.geometry) AS n FROM "districts" d JOIN "schools" s ON s.code = d.code GROUP BY d.name'


class StatementTest(unittest.TestCase):
    def test_a_select_and_a_with_select_pass_without_a_trailing_semicolon_or_comment(self):
        self.assertEqual(checked_sql("  SELECT 1;  "), "SELECT 1")
        self.assertEqual(checked_sql('SELECT name FROM "districts" -- the names'), 'SELECT name FROM "districts"')
        cte = 'WITH big AS (SELECT * FROM "districts" WHERE pop > 1) SELECT count(*) FROM big;;'
        self.assertEqual(checked_sql(cte), cte.rstrip(";"))

    def test_anything_but_a_select_is_refused(self):
        for sql in (
            'DELETE FROM "districts"',
            'UPDATE "districts" SET pop = 0',
            'INSERT INTO "districts" VALUES (1)',
            'DROP TABLE "districts"',
            "ATTACH DATABASE '/tmp/x.db' AS x",
            "PRAGMA table_info(districts)",
            "VACUUM INTO '/tmp/copy.db'",
            "EXPLAIN SELECT 1",
            "(SELECT 1)",
        ):
            with self.subTest(sql=sql), self.assertRaisesRegex(ValueError, "Only a read-only SELECT"):
                checked_sql(sql)

    def test_a_with_clause_must_end_in_a_select(self):
        with self.assertRaisesRegex(ValueError, "not DELETE"):
            checked_sql('WITH gone AS (SELECT fid FROM "districts") DELETE FROM "districts"')
        with self.assertRaisesRegex(ValueError, "not REPLACE"):
            checked_sql("WITH x AS (SELECT 1) REPLACE INTO t VALUES (1)")

    def test_a_second_statement_is_refused(self):
        for sql in ('SELECT 1; DROP TABLE "districts"', "SELECT 1; SELECT 2", "SELECT 1; -- x\n SELECT 2"):
            with self.subTest(sql=sql), self.assertRaisesRegex(ValueError, "Only one statement"):
                checked_sql(sql)

    def test_quotes_and_comments_hide_what_looks_like_sql(self):
        sql = "SELECT 'a; DROP TABLE x' AS t, \"odd;name\" FROM \"x\" /* ; DELETE */ WHERE note = 'it''s'"
        self.assertEqual(checked_sql(sql), sql)
        self.assertEqual(
            checked_sql("SELECT replace(name, 'a', 'b') FROM \"x\""), "SELECT replace(name, 'a', 'b') FROM \"x\""
        )

    def test_empty_and_unterminated_text_is_refused(self):
        for sql in ("", "   ", ";", "-- only a comment"):
            with self.subTest(sql=sql), self.assertRaisesRegex(ValueError, "sql is empty"):
                checked_sql(sql)
        with self.assertRaisesRegex(ValueError, "unterminated string"):
            checked_sql("SELECT 'open")
        with self.assertRaisesRegex(ValueError, "unterminated quoted name"):
            checked_sql('SELECT * FROM "districts')

    def test_functions_that_touch_files_or_the_database_are_refused(self):
        for sql in (
            "SELECT BlobToFile(x'00', '/tmp/a')",
            "SELECT load_extension('evil')",
            "SELECT \"ImportSHP\"('/tmp/a', 't', 'UTF-8')",
            "SELECT ExportGeoJSON2('t', 'geometry', '/tmp/a.geojson')",
            "SELECT CreateSpatialIndex('t', 'geometry')",
            "SELECT name FROM t WHERE BlobFromFile('/etc/passwd') IS NOT NULL",
        ):
            with self.subTest(sql=sql), self.assertRaisesRegex(ValueError, r"is not allowed here"):
                checked_sql(sql)
        checked_sql('SELECT ST_Area(ST_Transform(geometry, 32637)), ST_Buffer(geometry, 1) FROM "districts"')

    def test_identifiers_skip_functions_and_qualified_columns(self):
        names = identifiers(tokenize(JOIN))
        self.assertIn("districts", names)
        self.assertIn("schools", names)
        self.assertNotIn("count", names)
        self.assertNotIn("name", names, "d.name is a column of an alias")
        self.assertNotIn("code", names, "s.code and d.code are columns of an alias")
        self.assertEqual(identifiers(tokenize('SELECT "say ""hi""" FROM [my layer]')), ['say "hi"', "my layer"])

    def test_a_short_form_for_people(self):
        self.assertEqual(short_sql("SELECT  a\n FROM b"), "SELECT a FROM b")
        long = "SELECT " + ", ".join(f"field_{index}" for index in range(40)) + ' FROM "districts"'
        shown = short_sql(long)
        self.assertLessEqual(len(shown), SUMMARY_CHARS)
        self.assertTrue(shown.endswith("…"))


class Kind:
    def __init__(self, name):
        self.name = name


class Crs:
    def __init__(self, authid):
        self._authid = authid

    def authid(self):
        return self._authid


class Error:
    def __init__(self, text):
        self._text = text

    def summary(self):
        return self._text


class Provider:
    def __init__(self, text):
        self._text = text

    def error(self):
        return Error(self._text)


class Fields:
    def __init__(self, names):
        self._names = list(names)

    def names(self):
        return list(self._names)


class Feature:
    def __init__(self, values):
        self._values = list(values)

    def attributes(self):
        return list(self._values)


class Result:
    """What the next virtual layer reads as: its columns, rows, geometry, or the provider's error."""

    def __init__(self, columns=(), rows=(), geometry="", error="", total=None):
        self.columns, self.rows, self.geometry, self.error, self.total = (
            list(columns),
            list(rows),
            geometry,
            error,
            total,
        )


class Definition:
    def __init__(self):
        self.sources, self.query = [], ""

    def addSource(self, name, ref):
        self.sources.append([name, ref])

    def setQuery(self, query):
        self.query = query

    def toString(self):
        return json.dumps({"sources": self.sources, "query": self.query})


class Vector(QgsVectorLayer):
    """A project layer, or — built with the virtual provider — the query layer Vector.planned describes."""

    planned = Result()
    built = []

    def __init__(self, source="", name="", provider="memory", layer_id=""):
        self._name, self._provider = name, provider
        self._id = layer_id or f"{name}_id"
        self.result = Result()
        self.definition = {}
        if provider == "virtual":
            self.definition = json.loads(source)
            self.result = Vector.planned
            Vector.built.append(self)

    def name(self):
        return self._name

    def id(self):
        return self._id

    def providerType(self):
        return self._provider

    def isValid(self):
        return not self.result.error

    def dataProvider(self):
        return Provider(self.result.error)

    def fields(self):
        return Fields(self.result.columns)

    def getFeatures(self, request=None):
        return iter([Feature(row) for row in self.result.rows])

    def featureCount(self):
        return self.result.total if self.result.total is not None else len(self.result.rows)

    def isSpatial(self):
        return bool(self.result.geometry)

    def geometryType(self):
        return Kind(self.result.geometry.capitalize() + "Geometry")

    def crs(self):
        return Crs("EPSG:4326")


class Raster:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def id(self):
        return f"{self._name}_id"


class Project:
    def __init__(self, layers):
        self.layers = {layer.id(): layer for layer in layers}

    def mapLayers(self):
        return dict(self.layers)

    def mapLayer(self, identifier):
        return self.layers.get(identifier)

    def mapLayersByName(self, name):
        return [layer for layer in self.layers.values() if layer.name() == name]

    def addMapLayer(self, layer, add_to_tree=True):
        self.layers[layer.id()] = layer
        return layer


class SqlCase(unittest.TestCase):
    def setUp(self):
        self.districts = Vector(name="districts")
        self.schools = Vector(name="schools")
        self.project = Project([self.districts, self.schools, Raster("dem")])
        holder = type("Holder", (), {"instance": staticmethod(lambda: self.project)})
        patches = [
            mock.patch.object(virtual_module, "QgsProject", holder),
            mock.patch.object(create_module, "QgsProject", holder),
            mock.patch.object(virtual_module, "QgsVectorLayer", Vector),
            mock.patch.object(virtual_module, "QgsVirtualLayerDefinition", Definition),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        Vector.planned = Result(["name", "n"], [["A", 2], ["B", 0]])
        Vector.built = []
        self.query = get_tool_by_name("query_sql")
        self.create = get_tool_by_name("create_sql_layer")


class SourcesTest(SqlCase):
    def test_each_named_layer_is_bound_by_id_under_the_name_the_sql_writes(self):
        sources = virtual_module.resolve_sources('SELECT * FROM "Districts" JOIN schools USING (code)')
        self.assertEqual(
            sources, [{"alias": "Districts", "id": "districts_id"}, {"alias": "schools", "id": "schools_id"}]
        )

    def test_an_id_rasters_and_columns(self):
        sources = virtual_module.resolve_sources('SELECT name FROM "schools_id", "dem"')
        self.assertEqual(sources, [{"alias": "schools_id", "id": "schools_id"}])

    def test_a_shared_name_is_refused_with_the_ids_to_choose_from(self):
        twin = Vector(name="districts", layer_id="districts_2")
        self.project.layers[twin.id()] = twin
        with self.assertRaisesRegex(ValueError, r"ambiguous: 2 project layers.*\[id=districts_2\].*by its id"):
            virtual_module.resolve_sources('SELECT * FROM "districts"')
        sources = virtual_module.resolve_sources('SELECT * FROM "districts_2"')
        self.assertEqual(sources, [{"alias": "districts_2", "id": "districts_2"}])

    def test_the_provider_error_loses_the_wrapper_and_keeps_the_reason(self):
        sql = 'SELEC name FROM "districts"'
        layer = Vector(name="q")
        layer.result = Result(
            error=f'Query execution error on CREATE TEMP VIEW _tview AS {sql}: 1 - near "SELEC": syntax error'
        )
        self.assertEqual(
            query_error(layer, sql),
            'The query failed: near "SELEC": syntax error. Fix the SQL (SQLite with SpatiaLite functions; '
            'each layer\'s geometry column is "geometry") and call again.',
        )
        layer.result = Result(error="Referenced table distrcts in query not found!")
        self.assertIn(
            'Tables are the project\'s vector layers, named in double quotes: "districts", "schools".',
            query_error(layer, sql),
        )


class QuerySqlTest(SqlCase):
    def test_rows_come_back_with_their_columns_and_count(self):
        result = self.query.execute({"sql": JOIN})
        self.assertEqual(result, {"columns": ["name", "n"], "rows": [["A", 2], ["B", 0]], "row_count": 2})
        definition = Vector.built[0].definition
        self.assertEqual(definition["sources"], [["districts", "districts_id"], ["schools", "schools_id"]])
        self.assertEqual(definition["query"], JOIN)

    def test_rows_past_the_cap_are_counted_not_sent(self):
        Vector.planned = Result(["n"], [[index] for index in range(MAX_ROWS + 1)], total=5000)
        result = self.query.execute({"sql": 'SELECT n FROM "schools"'})
        self.assertEqual((len(result["rows"]), result["shown"], result["row_count"]), (MAX_ROWS, MAX_ROWS, 5000))
        self.assertIn("ORDER BY ... LIMIT", result["note"])

    def test_geometry_is_named_not_sent(self):
        Vector.planned = Result(["name"], [["A"]], geometry="polygon")
        result = self.query.execute({"sql": 'SELECT name, geometry FROM "districts"'})
        self.assertEqual((result["geometry"], result["crs"]), ("polygon", "EPSG:4326"))
        self.assertIn("not sent", result["geometry_note"])
        self.assertNotIn("geometry", result["columns"])

    def test_an_empty_result_says_so(self):
        Vector.planned = Result(["name"], [])
        result = self.query.execute({"sql": 'SELECT name FROM "districts" WHERE 0'})
        self.assertEqual((result["rows"], result["row_count"]), ([], 0))
        self.assertIn("No rows", result["note"])

    def test_long_text_and_binary_cells_are_cut(self):
        self.assertEqual(cell("x" * (MAX_TEXT_CHARS + 50)), "x" * MAX_TEXT_CHARS + "…")
        self.assertEqual(cell(b"\x00\x01\x02"), "<binary, 3 bytes>")
        self.assertEqual(cell(None), None)
        self.assertEqual(cell(2.5), 2.5)

    def test_invalid_sql_comes_back_as_the_providers_reason(self):
        Vector.planned = Result(error="Query preparation error on PRAGMA table_info(_tview): no such column: nme")
        with self.assertRaisesRegex(ValueError, "^The query failed: no such column: nme. Fix the SQL"):
            self.query.execute({"sql": 'SELECT nme FROM "districts"'})
        with self.assertRaisesRegex(ValueError, "Only a read-only SELECT"):
            self.query.execute({"sql": 'DELETE FROM "districts"'})
        self.assertEqual(Vector.built[1:], [], "a refused statement never reaches the provider")


class CreateSqlLayerTest(SqlCase):
    def test_prepare_checks_the_query_and_keeps_its_layers_privately(self):
        prepared = self.create.prepare({"sql": JOIN, "name": " school counts "})
        self.assertEqual(prepared["name"], "school counts")
        self.assertEqual([source["id"] for source in prepared[SOURCES_KEY]], ["districts_id", "schools_id"])
        self.assertNotIn(SOURCES_KEY, _model_line(ToolCall("c", "create_sql_layer", prepared)))
        self.assertNotIn("school counts", [layer.name() for layer in self.project.layers.values()])

    def test_prepare_refuses_a_taken_name_and_a_failing_query(self):
        with self.assertRaisesRegex(ValueError, "already in the project"):
            self.create.prepare({"sql": JOIN, "name": "schools"})
        with self.assertRaisesRegex(ValueError, "name is empty"):
            self.create.prepare({"sql": JOIN, "name": ""})
        Vector.planned = Result(error="Referenced table distrcts in query not found!")
        with self.assertRaisesRegex(ValueError, 'distrcts in query not found.*"districts", "schools"'):
            self.create.prepare({"sql": 'SELECT * FROM "distrcts"', "name": "x"})

    def test_execute_adds_the_planned_query_and_confirms_it(self):
        prepared = self.create.prepare({"sql": JOIN, "name": "school counts"})
        # The source was renamed after planning: the query still reads it by id.
        self.districts._name = "boroughs"
        payload = self.create.execute(prepared)
        added = self.project.mapLayer(payload["layer_id"])
        self.assertEqual(added.definition["sources"][0], ["districts", "districts_id"])
        self.assertEqual(
            (payload["layer_name"], payload["feature_count"], payload["geometry"]), ("school counts", 2, None)
        )
        self.assertTrue(self.create.confirm_applied(prepared, payload))
        self.assertFalse(self.create.confirm_applied(prepared, {"layer_id": "gone"}))
        self.assertFalse(self.create.confirm_applied({**prepared, "name": "other"}, payload))

    def test_a_source_removed_before_apply_stops_the_step(self):
        prepared = self.create.prepare({"sql": JOIN, "name": "school counts"})
        del self.project.layers["schools_id"]
        with self.assertRaisesRegex(ValueError, "Layer 'schools', which the query reads, is no longer in the project"):
            self.create.execute(prepared)


class SummaryTest(unittest.TestCase):
    def test_calls_read_as_the_sql_and_the_name(self):
        self.assertEqual(str(summarize_tool_call("query_sql", {"sql": "SELECT 1"})), "Running SQL: SELECT 1")
        line = summarize_tool_call("create_sql_layer", {"sql": JOIN, "name": "school counts"})
        self.assertTrue(str(line).startswith("Adding layer 'school counts' from SQL: SELECT d.name"))
        self.assertTrue(str(line).endswith("…"))
        for name in ("query_sql", "create_sql_layer"):
            with self.subTest(tool=name):
                self.assertTrue(get_tool_by_name(name).summarize_call({"sql": None, "name": None}).strip())

    def test_results_count_rows_and_features(self):
        self.assertEqual(summarize_tool_result("query_sql", {}, {"row_count": 12}), "12 rows")
        self.assertEqual(summarize_tool_result("create_sql_layer", {}, {"feature_count": 1}), "1 feature")
        self.assertEqual(summarize_tool_result("create_sql_layer", {}, {"feature_count_note": "remote"}), "")

    def test_the_tools_are_a_read_and_a_write_of_the_sql_skill(self):
        self.assertTrue(get_tool_by_name("query_sql").is_read_only)
        self.assertFalse(get_tool_by_name("create_sql_layer").is_read_only)
        self.assertEqual({get_tool_by_name(name).skill for name in ("query_sql", "create_sql_layer")}, {"sql"})


if __name__ == "__main__":
    unittest.main()
