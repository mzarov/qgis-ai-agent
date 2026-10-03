import json
import os
import tempfile
import time
import unittest
from unittest import mock

from ai_agent.core.agent.transcript import MAX_RESULT_CHARS
from ai_agent.qgis_tools.common import layers as layers_module
from ai_agent.qgis_tools.tables import load_table as load_module
from ai_agent.qgis_tools.tables import source as source_module
from ai_agent.qgis_tools.tables.coordinates import (
    WGS84,
    checked_wkt_crs,
    checked_xy_crs,
    guess_coordinates,
)
from ai_agent.qgis_tools.tables.delimited import (
    BOOLEAN,
    CYRILLIC_ENCODING,
    DOUBLE,
    INTEGER,
    SCAN_BYTES,
    TEXT,
    UTF8,
    UTF16,
    field_names,
    looks_like_file,
    read_table,
)
from ai_agent.qgis_tools.tables.keys import file_key_texts, key_text, match_report
from ai_agent.qgis_tools.tables.load_table import LoadTableTool
from ai_agent.qgis_tools.tables.preview_table import PreviewTableTool

DISTRICT_STATS = "code;name;pop;share\n001;Alpha;1200;0,5\n002;Beta;3400;1,25\n010;Gamma;;2\n"
CAFES = "name,lon,lat\nDome,2.33,48.84\nFlore,2.332,48.854\n"


class FakeProject:
    def __init__(self, layers=()):
        self.layers = {layer.id(): layer for layer in layers}
        self.added = []

    def mapLayers(self):
        return dict(self.layers)

    def mapLayersByName(self, name):
        return [layer for layer in self.layers.values() if layer.name() == name]

    def addMapLayer(self, layer, add_to_tree=True):
        self.added.append(layer)
        self.layers[layer.id()] = layer
        return layer

    def removeMapLayer(self, identifier):
        self.layers.pop(identifier, None)


def project_patch(project):
    holder = type("Holder", (), {"instance": staticmethod(lambda: project)})
    return [mock.patch.object(module, "QgsProject", holder) for module in (source_module, load_module, layers_module)]


class Crs:
    """EPSG:326xx is projected, anything else with an authority id is in degrees."""

    def __init__(self, text=""):
        self.text = text if ":" in text or text == "" else ("EPSG:4326" if text == "WGS84" else "")

    def isValid(self):
        return bool(self.text)

    def createFromUserInput(self, text):
        self.__init__(text)
        return self.isValid()

    def authid(self):
        return self.text

    def isGeographic(self):
        return not self.text.startswith("EPSG:326")


class FileCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def write(self, name, text, encoding="utf-8"):
        path = os.path.join(self.folder.name, name)
        with open(path, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        return path


class ReadTableTest(FileCase):
    def test_semicolons_decimal_commas_and_leading_zeros(self):
        table = read_table(self.write("stats.csv", DISTRICT_STATS))
        self.assertEqual(table.delimiter, ";")
        self.assertEqual(table.header, ["code", "name", "pop", "share"])
        self.assertTrue(table.decimal_comma)
        self.assertEqual(table.text_codes(), ["code"])
        types = [table.column_type(column) for column in table.header]
        self.assertEqual(types, [TEXT, TEXT, INTEGER, DOUBLE])
        self.assertTrue(table.complete)
        self.assertEqual(table.stem, "stats")

    def test_header_and_types_follow_the_provider(self):
        self.assertEqual(field_names([" a ", "a", "", "a"]), ["a", "a_1", "field_3", "a_2"])
        table = read_table(self.write("flags.csv", "paved,lit,id\nyes,1,1\nNo,0,2\n"))
        self.assertEqual([table.column_type(column) for column in table.header], [BOOLEAN, BOOLEAN, INTEGER])

    def test_utf16_binary_and_broken_quotes(self):
        path = os.path.join(self.folder.name, "excel.txt")
        with open(path, "wb") as handle:
            handle.write("code\tname\n001\tМосква\n".encode("utf-16"))
        table = read_table(path)
        self.assertEqual((table.encoding, table.delimiter_name, table.header), (UTF16, "tab", ["code", "name"]))
        binary = os.path.join(self.folder.name, "data.csv")
        with open(binary, "wb") as handle:
            handle.write(b"PK\x03\x04\x00\x00binary")
        with self.assertRaisesRegex(ValueError, "binary file"):
            read_table(binary)
        huge = self.write("quote.csv", 'a,b\n1,"' + "x" * 200_000 + "\n")
        with self.assertRaisesRegex(ValueError, "could not be split into columns.*unclosed quote"):
            read_table(huge, limit=SCAN_BYTES)

    def test_file_urls_are_paths(self):
        path = self.write("my stats.csv", "a\n1\n")
        url = "file://" + path.replace(" ", "%20")
        self.assertEqual(read_table(url).path, os.path.abspath(path))

    def test_a_large_lon_lat_file_is_checked_quickly(self):
        lines = "".join(
            f"{index},cafe {index},{37 + index % 1000 / 1000},{55 + index % 900 / 1000}\n" for index in range(200_000)
        )
        path = self.write("big.csv", "id,name,lon,lat\n" + lines)
        started = time.monotonic()
        table = read_table(path, limit=SCAN_BYTES)
        guess = guess_coordinates(table)
        checked_xy_crs(table, guess.x_field, guess.y_field, "")
        self.assertGreater(os.path.getsize(path), 5_000_000)
        self.assertLess(time.monotonic() - started, 5, "coordinate checks must stay linear in the file size")

    def test_tabs_pipes_and_a_forced_delimiter(self):
        self.assertEqual(read_table(self.write("a.tsv", "a\tb\n1\t2\n")).delimiter_name, "tab")
        self.assertEqual(read_table(self.write("b.txt", "a|b|c\n1|2|3\n")).delimiter, "|")
        forced = read_table(self.write("c.csv", "a;b,c\n1;2,3\n"), delimiter=",")
        self.assertEqual(forced.header, ["a;b", "c"])
        with self.assertRaisesRegex(ValueError, "Unsupported delimiter"):
            read_table(self.write("d.csv", "a\n"), delimiter="#")

    def test_encodings(self):
        self.assertEqual(read_table(self.write("bom.csv", "\ufeffcode,name\n1,a\n")).header, ["code", "name"])
        russian = read_table(self.write("ru.csv", "код;район\n1;Центральный\n", encoding="cp1251"))
        self.assertEqual(russian.encoding, CYRILLIC_ENCODING)
        self.assertEqual(russian.header, ["код", "район"])
        self.assertEqual(read_table(self.write("u.csv", "a,b\n1,2\n")).encoding, UTF8)

    def test_a_large_file_is_sampled_not_read_whole(self):
        path = self.write("big.csv", "id,v\n" + "".join(f"{i},{i * 2}\n" for i in range(5000)))
        table = read_table(path, limit=200)
        self.assertFalse(table.complete)
        self.assertTrue(all(len(row) == 2 for row in table.rows), "a cut line must not become a row")

    def test_paths_that_cannot_be_tables(self):
        with self.assertRaisesRegex(ValueError, "no file"):
            read_table(os.path.join(self.folder.name, "gone.csv"))
        with self.assertRaisesRegex(ValueError, "not a delimited text file.*add_layer"):
            read_table(self.write("roads.geojson", "{}"))
        with self.assertRaisesRegex(ValueError, "empty"):
            read_table(self.write("empty.csv", "\n\n"))
        with self.assertRaisesRegex(ValueError, "No file path"):
            read_table("  ")

    def test_missing_columns_name_the_real_ones(self):
        table = read_table(self.write("stats.csv", DISTRICT_STATS))
        with self.assertRaisesRegex(ValueError, "no column 'Code'.*Similar: code.*Available columns: code, name"):
            table.require_columns(["Code"])

    def test_a_table_argument_is_a_file_only_when_it_looks_like_one(self):
        self.assertTrue(looks_like_file("/data/pop.csv"))
        self.assertTrue(looks_like_file(self.write("pop.csv", "a\n")))
        self.assertFalse(looks_like_file("population"))
        self.assertFalse(looks_like_file("pop.csv"))


class CoordinatesTest(FileCase):
    def test_lon_lat_by_name_in_degrees(self):
        guess = guess_coordinates(read_table(self.write("cafes.csv", CAFES)))
        self.assertEqual((guess.x_field, guess.y_field, guess.crs), ("lon", "lat", WGS84))

    def test_projected_numbers_get_no_crs(self):
        table = read_table(self.write("p.csv", "id;X;Y\n1;412345,5;6123456\n"))
        guess = guess_coordinates(table)
        self.assertEqual((guess.x_field, guess.crs), ("X", ""))
        with self.assertRaisesRegex(ValueError, "not longitude/latitude.*Pass crs"):
            checked_xy_crs(table, "X", "Y", "")
        self.assertEqual(checked_xy_crs(table, "X", "Y", "EPSG:32637"), "EPSG:32637")
        with self.assertRaisesRegex(ValueError, "outside longitude/latitude"):
            checked_xy_crs(table, "X", "Y", "EPSG:4326", geographic=True)

    def test_swapped_columns_are_refused(self):
        table = read_table(self.write("cafes.csv", "name,lat,lon\nA,55.7,120.5\n"))
        with self.assertRaisesRegex(ValueError, "look swapped"):
            checked_xy_crs(table, "lat", "lon", "")

    def test_text_in_a_coordinate_column(self):
        table = read_table(self.write("c.csv", "x,y\n1,2\nn/a,3\n"))
        with self.assertRaisesRegex(ValueError, "'x' is not numeric \\('n/a'\\)"):
            checked_xy_crs(table, "x", "y", "")

    def test_wkt_with_z_and_m(self):
        table = read_table(
            self.write(
                "z.csv",
                "id;wkt\n1;POINT Z (37.5 55.7 120)\n2;POINTZ(37.6 55.8 130)\n3;LINESTRING M (37 55 1, 38 56 2)\n",
            )
        )
        self.assertEqual(guess_coordinates(table).wkt_field, "wkt")
        self.assertEqual(checked_wkt_crs(table, "wkt", ""), WGS84)

    def test_wkt(self):
        table = read_table(self.write("w.csv", 'id,geom\n1,"POINT (37.5 55.7)"\n2,"LINESTRING (37 55, 38 56)"\n'))
        guess = guess_coordinates(table)
        self.assertEqual((guess.wkt_field, guess.crs), ("geom", WGS84))
        self.assertEqual(checked_wkt_crs(table, "geom", ""), WGS84)
        with self.assertRaisesRegex(ValueError, "does not hold WKT"):
            checked_wkt_crs(table, "id", "")


class KeysTest(unittest.TestCase):
    def test_key_text_follows_qvariant_to_string(self):
        self.assertEqual(key_text(1), "1")
        self.assertEqual(key_text(1.0), "1")
        self.assertEqual(key_text(1.5), "1.5")
        self.assertEqual(key_text("007"), "007")
        self.assertIsNone(key_text(None))
        self.assertIsNone(key_text(float("nan")))

    def test_file_keys_take_the_column_type(self):
        self.assertEqual(file_key_texts(["01", "2"], TEXT), {"01", "2"})
        self.assertEqual(file_key_texts(["+1", "2", ""], INTEGER), {"1", "2"})
        self.assertEqual(file_key_texts(["1,0", "2,5"], DOUBLE, decimal_comma=True), {"1", "2.5"})
        self.assertEqual(file_key_texts(["Yes", "no"], BOOLEAN), {"true", "false"})
        self.assertEqual(file_key_texts([" A "], TEXT), {" A "}, "QGIS keeps the spaces of text")

    def test_reports_and_hints(self):
        report = match_report({"1", "2", "3"}, {"1", "2", "9"})
        self.assertEqual((report["matched_keys"], report["unmatched_keys"]), (2, 1))
        self.assertEqual(report["unmatched_samples"], ["3"])
        self.assertNotIn("hint", report)
        self.assertIn("leading zeros", match_report({"7", "8"}, {"007", "008"})["hint"])
        self.assertIn("spaces", match_report({"A "}, {"A"})["hint"])
        self.assertIn("letter case", match_report({"abc"}, {"ABC"})["hint"])
        self.assertIn("No key value", match_report({"a"}, {"b"})["hint"])


class PreviewTableTest(FileCase):
    def test_preview_reports_columns_rows_coordinates_and_codes(self):
        tool = PreviewTableTool()
        path = self.write("stats.csv", DISTRICT_STATS)
        result = tool.execute({"path": path, "rows": 2})
        self.assertEqual(result["delimiter"], ";")
        self.assertEqual(result["columns"][0], {"name": "code", "type": "text"})
        self.assertEqual(result["rows"], [["001", "Alpha", "1200", "0,5"], ["002", "Beta", "3400", "1,25"]])
        self.assertEqual(result["row_count"], 3)
        self.assertTrue(result["decimal_comma"])
        self.assertIn("code", result["notes"][0])
        self.assertNotIn("coordinates", result)
        cafes = tool.execute({"path": self.write("cafes.csv", CAFES)})
        self.assertEqual(cafes["coordinates"], {"x_field": "lon", "y_field": "lat", "crs": WGS84})

    def test_a_wide_file_keeps_its_findings_within_the_result_cap(self):
        header = ",".join(["lon", "lat"] + [f"column_{index}" for index in range(120)])
        row = ",".join(["37.6", "55.7"] + ["some longer text value"] * 120)
        result = PreviewTableTool().execute(
            {"path": self.write("wide.csv", f"{header}\n" + f"{row}\n" * 20), "rows": 20}
        )
        text = json.dumps(result, ensure_ascii=False)
        self.assertLess(len(text), MAX_RESULT_CHARS)
        self.assertEqual(list(result)[:4], ["path", "delimiter", "encoding", "coordinates"])
        self.assertEqual(result["columns_omitted"], 82)
        self.assertGreaterEqual(len(result["rows"]), 1)


class LoadTablePrepareTest(FileCase):
    def setUp(self):
        super().setUp()
        self.tool = LoadTableTool()
        patches = [*project_patch(FakeProject()), mock.patch.object(load_module, "QgsCoordinateReferenceSystem", Crs)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_lon_lat_are_recognised_and_crs_filled(self):
        prepared = self.tool.prepare({"path": self.write("cafes.csv", CAFES)})
        self.assertEqual((prepared["x_field"], prepared["y_field"], prepared["crs"]), ("lon", "lat", WGS84))
        self.assertEqual((prepared["name"], prepared["delimiter"]), ("cafes", ","))
        self.assertTrue(os.path.isabs(prepared["path"]))

    def test_table_only_and_plain_tables_carry_no_geometry(self):
        path = self.write("cafes.csv", CAFES)
        prepared = self.tool.prepare({"path": path, "table_only": True})
        self.assertNotIn("x_field", prepared)
        stats = self.tool.prepare({"path": self.write("stats.csv", DISTRICT_STATS)})
        self.assertNotIn("crs", stats)
        with self.assertRaisesRegex(ValueError, "table_only loads no geometry"):
            self.tool.prepare({"path": path, "table_only": True, "x_field": "lon", "y_field": "lat"})

    def test_bad_arguments_are_refused_with_the_columns(self):
        path = self.write("cafes.csv", CAFES)
        with self.assertRaisesRegex(ValueError, "no column 'longitude'.*Available columns: name, lon, lat"):
            self.tool.prepare({"path": path, "x_field": "longitude", "y_field": "lat"})
        with self.assertRaisesRegex(ValueError, "go together.*name, lon, lat"):
            self.tool.prepare({"path": path, "x_field": "lon"})
        with self.assertRaisesRegex(ValueError, "either wkt_field"):
            self.tool.prepare({"path": path, "x_field": "lon", "y_field": "lat", "wkt_field": "name"})

    def test_projected_columns_found_by_name_need_a_crs(self):
        path = self.write("p.csv", "id,x,y\n1,412345,6123456\n")
        with self.assertRaisesRegex(ValueError, "x/y look like coordinates.*table_only"):
            self.tool.prepare({"path": path})
        self.assertEqual(self.tool.prepare({"path": path, "crs": "EPSG:32637"})["crs"], "EPSG:32637")

    def test_crs_spellings_are_normalised_and_checked(self):
        cafes = self.write("cafes.csv", "name,lat,lon\nA,55.7,120.5\n")
        with self.assertRaisesRegex(ValueError, "look swapped"):
            self.tool.prepare({"path": cafes, "x_field": "lat", "y_field": "lon", "crs": "4326"})
        with self.assertRaisesRegex(ValueError, "look swapped"):
            self.tool.prepare({"path": cafes, "x_field": "lat", "y_field": "lon", "crs": "WGS84"})
        prepared = self.tool.prepare({"path": cafes, "x_field": "lon", "y_field": "lat", "crs": "4326"})
        self.assertEqual(prepared["crs"], "EPSG:4326")
        with self.assertRaisesRegex(ValueError, "not a coordinate system"):
            self.tool.prepare({"path": cafes, "crs": "nonsense"})

    def test_a_taken_name_is_refused(self):
        taken = type("Layer", (), {"name": lambda self: "cafes", "id": lambda self: "cafes_1"})()
        project = FakeProject([taken])
        for patch in project_patch(project):
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaisesRegex(ValueError, "already in the project"):
            self.tool.prepare({"path": self.write("cafes.csv", CAFES)})


class Query:
    def __init__(self):
        self.items = []

    def addQueryItem(self, key, value):
        self.items.append((key, value))


class Url:
    def __init__(self, path):
        self.path, self.query = path, None

    @staticmethod
    def fromLocalFile(path):
        return Url(path)

    def setQuery(self, query):
        self.query = query

    def toEncoded(self):
        return (f"file://{self.path}?" + "&".join(f"{k}={v}" for k, v in self.query.items)).encode()


class DelimitedUriTest(FileCase):
    def test_uri_pins_codes_to_text_and_keeps_decimal_commas(self):
        table = read_table(self.write("stats.csv", DISTRICT_STATS))
        with mock.patch.object(source_module, "QUrlQuery", Query), mock.patch.object(source_module, "QUrl", Url):
            plain = source_module.delimited_uri(table)
            points = source_module.delimited_uri(table, x_field="lon", y_field="lat", crs=WGS84)
        self.assertIn("delimiter=;", plain)
        self.assertIn("decimalPoint=,", plain)
        self.assertIn("field=code:text", plain)
        self.assertIn("geomType=none", plain)
        self.assertIn("xField=lon&yField=lat&crs=EPSG:4326", points)
        self.assertNotIn("geomType", points)


if __name__ == "__main__":
    unittest.main()
