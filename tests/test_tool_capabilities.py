import unittest

from ai_agent.qgis_tools.base import (
    EGRESS_FEATURE_VALUES,
    EGRESS_IMAGE,
    EGRESS_METADATA,
    EGRESS_WEB_CONTENT,
    SAFETY_DESTRUCTIVE,
    SAFETY_READ,
    SAFETY_WRITE,
)
from ai_agent.qgis_tools.registry import ALL_TOOLS


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
