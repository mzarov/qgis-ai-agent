from abc import ABC, abstractmethod
from typing import Any


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

    def get_schema_for_prompt(self) -> str:
        """Одна строка для системного промпта: имя тула и параметры с краткими подсказками."""
        parts = [f"{self.name} — params:"]
        for p in self.params_schema:
            desc = p.get("description", "")
            if not p.get("required", True):
                desc = f"{desc} (опционально)"
            parts.append(f"  {p['name']}: {desc}")
        return "\n".join(parts)

    def get_manifest(self) -> dict[str, Any]:
        """Возвращает декларативный манифест тула для prompt и роутинга."""
        return {
            "name": self.name,
            "description": self.description,
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
