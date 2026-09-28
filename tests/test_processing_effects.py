import unittest
from unittest.mock import patch

from ai_agent.core.llm.transport import ToolCall
from ai_agent.core.orchestrator.planning import EFFECT_EXTERNAL, destructive_lines, plan_line
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_WRITE
from ai_agent.qgis_tools.processing.effects import writes_external_data
from ai_agent.qgis_tools.processing.run_processing import RunProcessingTool


class ProcessingEffectsTest(unittest.TestCase):
    def test_source_writes_require_destructive_confirmation_and_external_warning(self):
        for identifier in (
            "native:truncatetable",
            "native:createattributeindex",
            "native:createspatialindex",
            "native:zonalstatistics",
            "native:repairshapefile",
            "native:definecurrentprojection",
            "native:postgisexecuteandloadsql",
            "native:spatialiteexecutesqlregistered",
            "native:importintospatialiteregistered",
            "gdal:assignprojection",
            "gdal:overviews",
            "gdal:rasterize_over",
            "gdal:rasterize_over_fixed_value",
        ):
            with self.subTest(identifier=identifier):
                call = ToolCall(
                    "test", "run_processing", {"algorithm_id": identifier, "parameters": {"INPUT": "roads"}}
                )
                self.assertEqual(RunProcessingTool().safety_for(call.arguments), SAFETY_DESTRUCTIVE)
                self.assertTrue(RunProcessingTool().has_external_effect(call.arguments))
                self.assertIn(EFFECT_EXTERNAL, plan_line(call))
                self.assertEqual(len(destructive_lines([call])[0]), 1)

    def test_algorithms_creating_new_layers_remain_regular_writes(self):
        for identifier in (
            "native:buffer",
            "native:deletecolumn",
            "native:renametablefield",
            "gdal:cliprasterbymasklayer",
        ):
            with self.subTest(identifier=identifier):
                params = {"algorithm_id": identifier, "parameters": {"OUTPUT": "TEMPORARY_OUTPUT"}}
                self.assertEqual(RunProcessingTool().safety_for(params), SAFETY_WRITE)
                self.assertFalse(RunProcessingTool().has_external_effect(params))

    def test_unclassified_providers_are_not_assumed_reversible(self):
        for identifier in ("script:buffer", "model:buffer", "custom:buffer", "grass:v.out.postgis"):
            self.assertTrue(writes_external_data(identifier), identifier)

    def test_security_risk_flag_overrides_a_builtin_identifier(self):
        self.assertTrue(writes_external_data("native:buffer", security_risk=True))

    def test_prepare_binds_canonical_id_and_replaces_injected_flags(self):
        class Algorithm:
            @staticmethod
            def id():
                return "native:truncatetable"

        tool = RunProcessingTool()
        with (
            patch.object(tool, "_prepare", return_value=(Algorithm(), {"INPUT": "roads-id"})),
            patch("ai_agent.qgis_tools.processing.run_processing.destination_parameter_names", return_value=[]),
            patch("ai_agent.qgis_tools.processing.run_processing._security_risk", return_value=True),
        ):
            prepared = tool.prepare({"algorithm_id": "alias:truncate", "_algorithm_security_risk": False})
        self.assertEqual(prepared["algorithm_id"], "native:truncatetable")
        self.assertTrue(prepared["_algorithm_security_risk"])
        self.assertEqual(tool.safety_for(prepared), SAFETY_DESTRUCTIVE)
