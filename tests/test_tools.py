import unittest

from qgis_ai_agent.qgis_tools.base import (
    JSON_SCHEMA_TYPES,
    SAFETY_DESTRUCTIVE,
    SAFETY_READ,
    SAFETY_WRITE,
    BaseTool,
)
from qgis_ai_agent.qgis_tools.registry import ALL_TOOLS, get_tool_by_name


class ToolContractTest(unittest.TestCase):
    def test_names_are_unique(self):
        names = [tool.name for tool in ALL_TOOLS]
        self.assertEqual(len(names), len(set(names)))

    def test_every_tool_declares_skill_and_safety(self):
        for tool in ALL_TOOLS:
            self.assertTrue(tool.skill, tool.name)
            self.assertIn(tool.safety, (SAFETY_READ, SAFETY_WRITE, SAFETY_DESTRUCTIVE), tool.name)

    def test_every_tool_has_russian_description(self):
        for tool in ALL_TOOLS:
            self.assertTrue(tool.description.strip(), tool.name)

    def test_lookup_by_name(self):
        self.assertIs(
            get_tool_by_name("list_layers").name and get_tool_by_name("list_layers"), get_tool_by_name("list_layers")
        )
        self.assertIsNone(get_tool_by_name("нет_такого"))


class SchemaTest(unittest.TestCase):
    def test_schema_shape(self):
        for tool in ALL_TOOLS:
            schema = tool.get_openai_schema()
            self.assertEqual(schema["type"], "function", tool.name)
            function = schema["function"]
            self.assertEqual(function["name"], tool.name)
            self.assertTrue(function["description"], tool.name)
            self.assertEqual(function["parameters"]["type"], "object", tool.name)

    def test_required_names_exist_in_properties(self):
        for tool in ALL_TOOLS:
            parameters = tool.get_openai_schema()["function"]["parameters"]
            for name in parameters["required"]:
                self.assertIn(name, parameters["properties"], f"{tool.name}: {name}")

    def test_declared_types_are_valid_json_schema(self):
        for tool in ALL_TOOLS:
            for parameter in tool.params_schema:
                self.assertIn(parameter.get("type", "string"), JSON_SCHEMA_TYPES, tool.name)

    def test_constraints_reach_the_model(self):
        for tool in ALL_TOOLS:
            if tool.constraints:
                self.assertIn(tool.constraints[0], tool.build_description(), tool.name)

    def test_summarize_call_returns_text(self):
        for tool in ALL_TOOLS:
            self.assertTrue(tool.summarize_call({}).strip(), tool.name)


class SafetyTest(unittest.TestCase):
    def test_read_tools_are_the_majority(self):
        read = [tool for tool in ALL_TOOLS if tool.is_read_only]
        self.assertGreater(len(read), 0)

    def test_is_read_only_matches_safety(self):
        for tool in ALL_TOOLS:
            self.assertEqual(tool.is_read_only, tool.safety == SAFETY_READ, tool.name)

    def test_prepare_defaults_to_passthrough(self):
        checked = []
        for tool in ALL_TOOLS:
            if tool.__class__.prepare is BaseTool.prepare:
                self.assertEqual(tool.prepare({"a": 1}), {"a": 1}, tool.name)
                checked.append(tool.name)
        self.assertTrue(checked)


if __name__ == "__main__":
    unittest.main()
