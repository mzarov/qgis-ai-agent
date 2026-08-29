import unittest

from qgis_ai_agent.qgis_tools.web import geocode as geocode_module
from qgis_ai_agent.qgis_tools.web import search_web as search_module
from qgis_ai_agent.qgis_tools.web.fetch_url import FetchUrlTool, _limit
from qgis_ai_agent.qgis_tools.web.geocode import GeocodeTool, parse_matches
from qgis_ai_agent.qgis_tools.web.html_text import html_to_text
from qgis_ai_agent.qgis_tools.web.http import checked_url
from qgis_ai_agent.qgis_tools.web.search_web import SearchWebTool, parse_results

PAGE = """<html><head><title>t</title><style>.a{color:red}</style></head>
<body><script>alert(1)</script><h1>Заголовок</h1><p>Первый  абзац &amp; хвост.</p>
<div>Второй<br>абзац</div></body></html>"""

DDG = (
    '<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fepsg.io%2F32639&amp;rut=x">'
    "EPSG:32639</a>"
    '<a class="result__snippet" href="#">WGS 84 / UTM zone <b>39N</b></a>'
    '<a class="result__a" href="https://example.org/page">Прямая ссылка</a>'
)

NOMINATIM = """[
 {"display_name": "Дивноморское, Краснодарский край", "category": "place", "type": "village",
  "lat": "44.5052", "lon": "38.1305", "boundingbox": ["44.49", "44.52", "38.11", "38.15"]},
 {"display_name": "Дивноморское шоссе", "category": "highway", "type": "residential",
  "lat": "44.51", "lon": "38.14"}
]"""


class HtmlTextTest(unittest.TestCase):
    def test_scripts_and_styles_are_dropped(self):
        text = html_to_text(PAGE)
        self.assertNotIn("alert", text)
        self.assertNotIn("color:red", text)

    def test_blocks_become_lines_and_entities_unescape(self):
        text = html_to_text(PAGE)
        self.assertIn("Заголовок", text)
        self.assertIn("Первый абзац & хвост.", text)
        self.assertIn("Второй\nабзац", text)

    def test_plain_text_survives(self):
        self.assertEqual(html_to_text("просто текст"), "просто текст")


class UrlTest(unittest.TestCase):
    def test_https_passes(self):
        self.assertEqual(checked_url(" https://a.b/c "), "https://a.b/c")

    def test_file_scheme_is_refused(self):
        with self.assertRaises(ValueError):
            checked_url("file:///etc/passwd")

    def test_empty_is_refused(self):
        with self.assertRaises(ValueError):
            checked_url("  ")

    def test_the_limit_is_clamped(self):
        self.assertEqual(_limit(999999), 20000)
        self.assertEqual(_limit(None), 6000)
        self.assertEqual(_limit(10), 200)


class SearchParseTest(unittest.TestCase):
    def test_results_carry_title_url_snippet(self):
        results = parse_results(DDG)
        self.assertEqual(results[0]["title"], "EPSG:32639")
        self.assertEqual(results[0]["url"], "https://epsg.io/32639")
        self.assertIn("39N", results[0]["snippet"])

    def test_a_direct_link_is_left_alone(self):
        self.assertEqual(parse_results(DDG)[1]["url"], "https://example.org/page")

    def test_no_results_parse_to_empty(self):
        self.assertEqual(parse_results("<html>nothing here</html>"), [])

    def test_the_tool_reads_through_the_fetcher(self):
        saved = search_module.get_text
        search_module.get_text = lambda url: DDG
        try:
            result = SearchWebTool().execute({"query": "epsg kazan"})
        finally:
            search_module.get_text = saved
        self.assertEqual(len(result["results"]), 2)

    def test_an_empty_query_is_refused(self):
        with self.assertRaises(ValueError):
            SearchWebTool().execute({"query": " "})


WIKI = """{"query": {"search": [
 {"title": "UTM-метки", "snippet": "<span class=\\"searchmatch\\">UTM</span>-метка"},
 {"title": "Казань", "snippet": "город"}
]}}"""


class WikipediaFallbackTest(unittest.TestCase):
    def test_wikipedia_hits_become_results_with_links(self):
        results = search_module.parse_wikipedia(WIKI, "ru")
        self.assertEqual(results[0]["title"], "UTM-метки")
        self.assertIn("ru.wikipedia.org/wiki/UTM-", results[0]["url"])
        self.assertEqual(results[0]["snippet"], "UTM-метка")

    def test_an_unreachable_engine_falls_back_to_wikipedia(self):
        saved = search_module.get_text

        def fake(url):
            if "duckduckgo" in url:
                raise ValueError("Could not fetch: timed out.")
            return WIKI

        search_module.get_text = fake
        try:
            result = SearchWebTool().execute({"query": "казань utm"})
        finally:
            search_module.get_text = saved
        self.assertEqual(result["engine"], "wikipedia")
        self.assertIn("Wikipedia", result["note"])

    def test_the_language_follows_the_query(self):
        seen = []
        saved = search_module.get_text

        def fake(url):
            seen.append(url)
            if "duckduckgo" in url:
                raise ValueError("down")
            return WIKI

        search_module.get_text = fake
        try:
            SearchWebTool().execute({"query": "казань"})
            SearchWebTool().execute({"query": "kazan"})
        finally:
            search_module.get_text = saved
        self.assertIn("ru.wikipedia", seen[1])
        self.assertIn("en.wikipedia", seen[3])


class GeocodeParseTest(unittest.TestCase):
    def test_matches_carry_coordinates_and_bbox(self):
        matches = parse_matches(NOMINATIM)
        self.assertEqual(matches[0]["lat"], 44.5052)
        self.assertEqual(matches[0]["bbox"], "38.11,44.49,38.15,44.52")
        self.assertEqual(matches[0]["type"], "place/village")

    def test_a_match_without_bbox_still_comes_back(self):
        self.assertNotIn("bbox", parse_matches(NOMINATIM)[1])

    def test_broken_json_parses_to_empty(self):
        self.assertEqual(parse_matches("{oops"), [])

    def test_the_tool_credits_openstreetmap(self):
        saved = geocode_module.get_text
        geocode_module.get_text = lambda url: NOMINATIM
        try:
            result = GeocodeTool().execute({"place": "Дивноморское"})
        finally:
            geocode_module.get_text = saved
        self.assertIn("OpenStreetMap", result["attribution"])


class FetchToolTest(unittest.TestCase):
    def test_html_is_stripped_and_truncated(self):
        import qgis_ai_agent.qgis_tools.web.fetch_url as module

        saved = module.get_text
        module.get_text = lambda url: PAGE
        try:
            result = FetchUrlTool().execute({"url": "https://a.b", "max_chars": 200})
        finally:
            module.get_text = saved
        self.assertIn("Заголовок", result["text"])
        self.assertNotIn("<h1>", result["text"])

    def test_summaries_never_raise(self):
        for tool in (FetchUrlTool(), SearchWebTool(), GeocodeTool()):
            self.assertTrue(tool.summarize_call({}).strip())


if __name__ == "__main__":
    unittest.main()
