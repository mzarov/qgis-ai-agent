import unittest
from unittest.mock import patch

from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.llm.transport import ToolCall
from ai_agent.core.orchestrator.planning import EFFECT_NETWORK, plan_line
from ai_agent.qgis_tools.base import (
    EGRESS_FEATURE_VALUES,
    EGRESS_IMAGE,
    EGRESS_METADATA,
    EGRESS_WEB_CONTENT,
    SAFETY_DESTRUCTIVE,
    SAFETY_READ,
    SAFETY_WRITE,
)
from ai_agent.qgis_tools.registry import ALL_TOOLS, get_tool_by_name

NETWORK_WRITES = ("download_osm", "run_overpass", "add_basemap", "add_service_layer")


class ExplicitCapabilitiesTest(unittest.TestCase):
    def test_every_registered_tool_explicitly_declares_its_effects(self):
        for tool in ALL_TOOLS:
            declared = vars(type(tool))
            with self.subTest(tool=tool.name):
                self.assertIn("safety", declared)
                self.assertIn(tool.safety, (SAFETY_READ, SAFETY_WRITE, SAFETY_DESTRUCTIVE))
                self.assertIn("egress", declared)
                self.assertIn(tool.egress, (EGRESS_METADATA, EGRESS_FEATURE_VALUES, EGRESS_IMAGE, EGRESS_WEB_CONTENT))
                for capability, resolver in (
                    ("external_effect", "has_external_effect"),
                    ("network_access", "has_network_access"),
                ):
                    self.assertTrue(capability in declared or resolver in declared, capability)
                    if capability in declared:
                        self.assertIsInstance(declared[capability], bool)


class NetworkWritesTest(unittest.TestCase):
    def test_downloads_declare_the_service_but_stay_writes(self):
        for name in NETWORK_WRITES:
            tool = get_tool_by_name(name)
            with self.subTest(tool=name):
                self.assertEqual(tool.safety, SAFETY_WRITE)
                self.assertTrue(tool.has_network_access({}))
                self.assertIn(EFFECT_NETWORK, plan_line(ToolCall("c", name, {})))

    def test_a_network_write_queues_without_staging_the_run(self):
        loop = AgentLoop()
        call = ToolCall("c", "add_basemap", {"preset": "osm"})
        with patch.object(get_tool_by_name("add_basemap"), "prepare", side_effect=lambda params: dict(params)):
            result = loop._dispatch(call)
        self.assertEqual(result.payload.get("status"), "queued")
        self.assertFalse(loop._staged)
        self.assertEqual([queued.name for queued in loop.pending_writes()], ["add_basemap"])
