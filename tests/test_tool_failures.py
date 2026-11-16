import json
import pathlib
import re
import unittest
from types import SimpleNamespace
from unittest import mock

from ai_agent.core import tool_failures, usage_payload
from ai_agent.core.agent import apply_run
from ai_agent.core.agent.batch_apply import BatchApplyMixin
from ai_agent.core.agent.dispatch import DispatchMixin
from ai_agent.core.agent.transcript import ToolResult
from ai_agent.core.llm.turns import ToolCall
from ai_agent.core.tool_failures import failure_reason
from ai_agent.qgis_tools.data.catalogue import TURNED_OFF
from ai_agent.qgis_tools.inspect.queries import SCAN_LIMIT_MESSAGE
from ai_agent.qgis_tools.processing.deadline import TIMED_OUT
from ai_agent.qgis_tools.python.sandbox import BUDGET_MESSAGE
from ai_agent.qgis_tools.web.http import FETCH_FAILED

SECRET_PARTS = ("Parcels 2024", "owner_name", "C:\\Users\\Ivan", "ivan:hunter2", "gis.example.com", "42.7")
# The texts the tools raise, with a layer, a field, a path, an address and a value a user could own.
CASES = (
    ("set_symbol", "Not run because the earlier planned step 'add_field' failed.", "skipped"),
    ("set_symbol", apply_run.CANCELLED_ERROR, "cancelled"),
    ("set_symbol", apply_run.PROJECT_CHANGED_ERROR, "cancelled"),
    ("load_dataset", TURNED_OFF.format(connector="Natural Earth"), "connector_off"),
    ("run_processing", TIMED_OUT.format(seconds=120), "timeout"),
    ("download_osm", "Could not fetch data from Overpass: server replied: Gateway Timeout. Retry later.", "timeout"),
    ("fetch_url", FETCH_FAILED.format(url="https://gis.example.com/a", reason="timed out"), "timeout"),
    (
        "describe_layer",
        "Layer name 'Parcels 2024' is ambiguous: 2 project layers match ('Parcels 2024' [id=p_1], "
        "'Parcels 2024' [id=p_2]). Pass the layer id from list_layers as layer_name.",
        "layer_ambiguous",
    ),
    ("query_layer", "Layer not found: 'Parcels 2024'. Available layers: 'roads' [id=roads_7].", "layer_not_found"),
    ("set_symbol", "The planned target layer 'Parcels 2024' changed or disappeared before apply.", "layer_not_found"),
    ("get_field_values", "Field not found: 'owner_name'. Did you mean 'OWNER'?", "field_not_found"),
    (
        "query_layer",
        "The expression in 'filter' refers to fields that do not exist: owner_name. "
        "The expression was: owner_name = 'Ivan' AND area > 42.7.",
        "field_not_found",
    ),
    (
        "query_layer",
        "Could not parse the expression in 'filter': syntax error, unexpected NAME. The expression was: area >> 42.7",
        "bad_expression",
    ),
    ("query_sql", "The query failed: no such column: owner_name. Check the column names.", "bad_expression"),
    ("query_layer", "Layer 'Parcels 2024' is not a vector layer, it cannot be queried.", "not_supported"),
    (
        "set_raster_style",
        "Layer 'Parcels 2024' is not a raster layer — use the vector styling tools instead.",
        "not_supported",
    ),
    (
        "update_attributes",
        "Layer 'Parcels 2024' cannot be switched into editing mode. Its data source is read-only.",
        "not_supported",
    ),
    ("download_osm", "Overpass ran fine, but nothing matches this query. Either the tag is wrong.", "no_result"),
    (
        "set_raster_style",
        "Band 1 has no value range (min equals max) — a colour ramp over it would be meaningless.",
        "no_result",
    ),
    ("search_web", FETCH_FAILED.format(url="https://gis.example.com/search", reason="HTTP 403"), "network"),
    (
        "download_osm",
        "Could not fetch data from Overpass: Error transferring "
        "https://ivan:hunter2@gis.example.com/api "  # pragma: allowlist secret
        "- server replied: Too Many Requests. Retry later.",
        "network",
    ),
    ("query_layer", SCAN_LIMIT_MESSAGE.format(limit=50000), "too_large"),
    ("download_osm", "Overpass returned 120 MB, which is over the limit of 80 MB.", "too_large"),
    ("add_field", "QGIS refused to add field 'owner_name'.", "qgis_refused"),
    (
        "run_processing",
        "native:buffer has no parameter 'DISTANSE'. Its parameters are: INPUT, DISTANCE.",
        "bad_arguments",
    ),
    ("set_raster_style", "band must be a whole number from 1 to 3.", "bad_arguments"),
    (
        "run_processing",
        "Unable to execute algorithm: Could not load source layer for INPUT: C:\\Users\\Ivan\\parcels.gpkg",
        "algorithm_failed",
    ),
    ("run_python", "name 'iface' is not defined", "snippet_failed"),
    ("run_python", "Layer not found: 'Parcels 2024' must be loaded first", "snippet_failed"),
    ("run_python", BUDGET_MESSAGE.format(limit=300), "timeout"),
    ("render_map", "Something nobody foresaw about C:\\Users\\Ivan\\map.png", "other"),
    ("render_map", "", "other"),
)


class FailureReasonTest(unittest.TestCase):
    def test_the_tools_own_texts_fall_under_their_reasons(self):
        for tool, error, reason in CASES:
            with self.subTest(error=error):
                self.assertEqual(failure_reason(tool, error), reason)

    def test_every_reason_of_the_list_has_a_text_that_reaches_it(self):
        self.assertEqual({reason for _tool, _error, reason in CASES}, set(tool_failures.REASONS))

    def test_only_a_listed_code_ever_comes_back(self):
        for tool, error, _reason in CASES:
            code = failure_reason(tool, error)
            self.assertIn(code, tool_failures.REASONS)
            self.assertFalse(any(part in code for part in SECRET_PARTS))

    def test_the_collector_accepts_exactly_the_reasons_the_plugin_sends(self):
        source = (pathlib.Path(__file__).parents[1] / "telemetry/worker/src/payload.js").read_text(encoding="utf-8")
        listed = re.search(r"REASON_VALUES = \[([^\]]*)\]", source)
        self.assertEqual(re.findall(r'"([a-z_]+)"', listed.group(1)), list(tool_failures.REASONS))
        versions = re.search(r"PING_VERSIONS = \[([^\]]*)\]", source)
        self.assertIn(str(usage_payload.PAYLOAD_VERSION), re.findall(r"\d+", versions.group(1)))


class ReasonsInThePayloadTest(unittest.TestCase):
    def setUp(self):
        for target, value in (
            ("get_api_url", lambda: "http://localhost:11434/v1"),
            ("get_dialect", lambda: "openai"),
            ("has_saved_model", lambda: True),
            ("plugin_version", lambda: "0.4.5"),
            ("locale_code", lambda: "en"),
        ):
            patcher = mock.patch.object(usage_payload, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _counted(self, failures):
        counts: dict = {}
        for tool, error in failures:
            usage_payload.add(counts, "tools", tool)
            usage_payload.add(counts, usage_payload.TOOL_ERRORS, tool)
            key = usage_payload.reason_key(tool, failure_reason(tool, error))
            usage_payload.add(counts, usage_payload.TOOL_REASONS, key)
        return counts

    def test_a_day_names_each_failed_tool_with_its_reasons_and_nothing_of_the_error(self):
        failures = [(tool, error) for tool, error, _reason in CASES if tool in ("query_layer", "download_osm")]
        sent = usage_payload.payload("1f0e…", "2026-11-16", self._counted(failures))
        self.assertEqual(sent["v"], 4)
        self.assertEqual(
            sent["tool_reasons"],
            {
                "query_layer": {
                    "layer_not_found": 1,
                    "field_not_found": 1,
                    "bad_expression": 1,
                    "not_supported": 1,
                    "too_large": 1,
                },
                "download_osm": {"timeout": 1, "no_result": 1, "network": 1, "too_large": 1},
            },
        )
        for tool, reasons in sent["tool_reasons"].items():
            self.assertEqual(sum(reasons.values()), sent["tool_errors"][tool])
        text = json.dumps(sent)
        for part in SECRET_PARTS:
            self.assertNotIn(part, text)

    def test_a_day_without_failures_sends_an_empty_map(self):
        self.assertEqual(usage_payload.payload("1f0e…", "2026-11-16", {"runs": 1})["tool_reasons"], {})

    def test_reasons_never_outnumber_the_errors_the_collector_checks_them_against(self):
        counts = {
            "tools": {"query_layer": 5},
            "tool_errors": {"query_layer": 2},
            "tool_reasons": {
                "query_layer/timeout": 2,
                "query_layer/other": 3,
                "query_layer/made_up": 1,
                "list_layers/other": 1,
            },
        }
        sent = usage_payload.payload("1f0e…", "2026-11-16", counts)
        self.assertEqual(sent["tool_reasons"], {"query_layer": {"timeout": 2}})

    def test_a_malformed_pair_is_not_counted(self):
        counts: dict = {}
        for key in ("query_layer", "query_layer/Layer 'Parcels 2024'", "Query Layer/other", "a/b/c d"):
            usage_payload.add(counts, usage_payload.TOOL_REASONS, key)
        self.assertEqual(counts[usage_payload.TOOL_REASONS], {})


class Signal:
    def __init__(self, seen=None):
        self.seen = seen

    def emit(self, *args):
        if self.seen is not None:
            self.seen.append(args)


class ErrorBehindTheSignalTest(unittest.TestCase):
    CALL = ToolCall(id="c1", name="query_layer", arguments={"layer_name": "Parcels 2024"})
    ERROR = "Layer not found: 'Parcels 2024'. Available layers: the project has no layers."

    def test_a_read_that_failed_leaves_its_english_text_for_the_counts(self):
        seen: list = []
        loop = DispatchMixin()
        loop.tool_started, loop.tool_finished, loop.visual_ready = Signal(), Signal(seen), Signal()
        loop._executor = SimpleNamespace(run=lambda call: ToolResult.failure(call, self.ERROR))
        self.assertEqual(loop.last_tool_error, "")
        loop._run_now(self.CALL)
        self.assertEqual(loop.last_tool_error, self.ERROR)
        self.assertEqual(seen[0][:2], ("query_layer", False))
        self.assertNotIn("Parcels", seen[0][2], "the signal carries the plain line, not the model's text")

    def test_an_applied_step_does_the_same_and_a_success_clears_it(self):
        loop = BatchApplyMixin()
        loop.tool_finished = Signal()
        loop._active_apply_call = self.CALL
        loop._is_current = lambda generation: True
        loop._on_apply_finish(self.CALL, ToolResult.failure(self.CALL, self.ERROR))
        self.assertEqual(loop.last_tool_error, self.ERROR)
        loop._active_apply_call = self.CALL
        loop._on_apply_finish(self.CALL, ToolResult(call=self.CALL, payload={"matched": 3}))
        self.assertEqual(loop.last_tool_error, "")


if __name__ == "__main__":
    unittest.main()
