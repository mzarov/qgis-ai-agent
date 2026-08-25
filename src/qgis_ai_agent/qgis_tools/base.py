from abc import ABC, abstractmethod
from typing import Any

SAFETY_READ = "read"
SAFETY_WRITE = "write"
SAFETY_DESTRUCTIVE = "destructive"

JSON_SCHEMA_TYPES = {
    "string": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    params_schema: list[dict[str, Any]] = []
    constraints: list[str] = []
    examples: list[str] = []
    skill: str = ""
    safety: str = SAFETY_WRITE

    @property
    def is_read_only(self) -> bool:
        return self.safety == SAFETY_READ

    def get_openai_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in self.params_schema:
            param_name = param.get("name")
            if not param_name:
                continue
            properties[param_name] = self._build_property(param)
            if param.get("required", True):
                required.append(param_name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.build_description(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @staticmethod
    def _build_property(param: dict[str, Any]) -> dict[str, Any]:
        kind = JSON_SCHEMA_TYPES.get(param.get("type", "string"), "string")
        prop: dict[str, Any] = {"type": kind, "description": param.get("description", "")}
        enum_values = param.get("enum")
        if enum_values:
            prop["enum"] = list(enum_values)
        if kind == "array":
            prop["items"] = param.get("items") or {"type": "string"}
        if kind == "object" and param.get("properties"):
            prop["properties"] = dict(param["properties"])
        return prop

    def build_description(self) -> str:
        parts = [self.description]
        if self.constraints:
            parts.append("Ограничения: " + "; ".join(self.constraints) + ".")
        if self.examples:
            parts.append("Примеры запросов: " + "; ".join(self.examples) + ".")
        return " ".join(part for part in parts if part)

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        return params

    def summarize_call(self, params: dict[str, Any]) -> str:
        if not params:
            return self.description or self.name
        shown = ", ".join(f"{key}={value}" for key, value in params.items())
        return f"{self.description or self.name}: {shown}"

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        ...
