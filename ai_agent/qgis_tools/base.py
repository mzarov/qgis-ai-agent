from abc import ABC, abstractmethod
from typing import Any

RESULT_IMAGE_KEY = "image_base64"
RESULT_VISUAL_KEY = "visual_for_user"
SAFETY_READ = "read"
SAFETY_WRITE = "write"
SAFETY_DESTRUCTIVE = "destructive"
EGRESS_METADATA = "metadata"
EGRESS_FEATURE_VALUES = "feature_values"
EGRESS_IMAGE = "image"
EGRESS_WEB_CONTENT = "web_content"

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
    egress: str = EGRESS_METADATA
    external_effect: bool = False
    network_access: bool = False
    returns_image: bool = False
    detail_is_code: bool = False

    def safety_for(self, params: dict[str, Any]) -> str:
        return self.safety

    def has_external_effect(self, params: dict[str, Any]) -> bool:
        return self.external_effect

    def has_network_access(self, params: dict[str, Any]) -> bool:
        return self.network_access

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
            parts.append("Constraints: " + "; ".join(self.constraints) + ".")
        if self.examples:
            parts.append("Example requests: " + "; ".join(self.examples) + ".")
        return " ".join(part for part in parts if part)

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        # No mutations or service calls: prepare runs before the user confirms.
        return params

    def detail_call(self, params: dict[str, Any]) -> str:
        return ""

    def summarize_call(self, params: dict[str, Any]) -> str:
        if not params:
            return self.description or self.name
        shown = ", ".join(f"{key}={value}" for key, value in params.items())
        return f"{self.description or self.name}: {shown}"

    def summarize_result(self, params: dict[str, Any], payload: dict[str, Any]) -> str:
        return ""

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        return None

    def start(self, params: dict[str, Any]) -> Any:
        return None

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> dict[str, Any]: ...
