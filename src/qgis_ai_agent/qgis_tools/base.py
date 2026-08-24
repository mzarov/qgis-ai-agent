from abc import ABC, abstractmethod
from typing import Any

SAFETY_READ = "read"
SAFETY_WRITE = "write"
SAFETY_DESTRUCTIVE = "destructive"

# Соответствие типов из params_schema типам JSON Schema.
_JSON_SCHEMA_TYPES = {
    "string": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


class BaseTool(ABC):
    """
    Базовый класс инструмента агента. Все тулы в qgis_tools наследуют его
    и задают имя, описание, схему параметров для LLM и логику выполнения.
    """
    name: str = ""
    description: str = ""
    params_schema: list[dict[str, Any]] = []
    capabilities: list[str] = []
    examples: list[str] = []
    constraints: list[str] = []
    # Домен, к которому принадлежит тул: определяет, с каким скиллом он грузится.
    skill: str = ""
    # Класс безопасности: read выполняется сразу, write копится на подтверждение.
    safety: str = SAFETY_WRITE

    @property
    def is_read_only(self) -> bool:
        """Тул только читает состояние проекта и не требует подтверждения."""
        return self.safety == SAFETY_READ

    def get_openai_schema(self) -> dict[str, Any]:
        """Описание тула в формате OpenAI function calling."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in self.params_schema:
            param_name = param.get("name")
            if not param_name:
                continue
            json_type = _JSON_SCHEMA_TYPES.get(param.get("type", "string"), "string")
            prop: dict[str, Any] = {
                "type": json_type,
                "description": param.get("description", ""),
            }
            enum_values = param.get("enum")
            if enum_values:
                prop["enum"] = list(enum_values)
            properties[param_name] = prop
            if param.get("required", True):
                required.append(param_name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self._build_full_description(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def _build_full_description(self) -> str:
        """Описание тула с ограничениями — попадает в схему для модели."""
        parts = [self.description]
        if self.constraints:
            parts.append("Ограничения: " + "; ".join(self.constraints) + ".")
        return " ".join(part for part in parts if part)

    def summarize_call(self, params: dict[str, Any]) -> str:
        """
        Человекочитаемое описание вызова для чата.
        Переопределяется в тулах, где важна понятная формулировка.
        """
        if not params:
            return self.description or self.name
        shown = ", ".join(f"{key}={value}" for key, value in params.items())
        return f"{self.description or self.name}: {shown}"

    def get_manifest(self) -> dict[str, Any]:
        """Возвращает декларативный манифест тула для prompt и роутинга."""
        return {
            "name": self.name,
            "description": self.description,
            "skill": self.skill,
            "safety": self.safety,
            "capabilities": list(self.capabilities),
            "constraints": list(self.constraints),
            "examples": list(self.examples),
            "params_schema": list(self.params_schema),
        }

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Выполняет шаг. params — словарь из JSON плана модели.
        Возвращает результат для оркестратора (например layout_name).
        """
        pass
