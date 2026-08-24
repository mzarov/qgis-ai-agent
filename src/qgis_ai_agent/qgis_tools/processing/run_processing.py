from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.processing.utils import (
    coerce_parameters,
    find_algorithm,
    normalize_output,
)


class RunProcessingTool(BaseTool):
    """Запуск любого алгоритма обработки QGIS по идентификатору и параметрам."""
    name = "run_processing"
    description = (
        "Запустить алгоритм обработки QGIS с заданными параметрами. "
        "Сначала уточните сигнатуру через describe_processing. "
        "По умолчанию результат добавляется в проект."
    )
    skill = "processing"
    safety = SAFETY_WRITE
    capabilities = ["processing:run"]
    examples = ["Построй буфер 500 метров вокруг дорог"]
    constraints = [
        "Идентификатор алгоритма должен существовать в реестре",
        "Имена параметров должны точно совпадать с describe_processing",
    ]
    params_schema = [
        {
            "name": "algorithm_id",
            "type": "string",
            "description": "Идентификатор алгоритма, например native:buffer",
            "required": True,
        },
        {
            "name": "parameters",
            "type": "object",
            "description": (
                "Объект с параметрами алгоритма. Слои указываются по имени, "
                "выход обычно 'TEMPORARY_OUTPUT'."
            ),
            "required": True,
        },
        {
            "name": "load_output",
            "type": "boolean",
            "description": "Добавить результат в проект (по умолчанию true)",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага запуска алгоритма."""
        algorithm_id = (params.get("algorithm_id") or "").strip()
        arguments = params.get("parameters") or {}
        shown = ", ".join(f"{key}={value}" for key, value in list(arguments.items())[:3])
        tail = "…" if len(arguments) > 3 else ""
        return f"Запустить {algorithm_id} ({shown}{tail})."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        algorithm = find_algorithm(params.get("algorithm_id") or "")
        arguments = params.get("parameters")
        if not isinstance(arguments, dict):
            raise ValueError("Параметр parameters должен быть объектом.")
        load_output = params.get("load_output")
        load_output = True if load_output is None else bool(load_output)

        try:
            import processing
        except ImportError:
            raise RuntimeError(
                "Модуль Processing недоступен. Включите его в Модули → Управление модулями."
            )

        # Модель присылает enum-варианты подписью, а выход часто вовсе не указывает.
        prepared = coerce_parameters(algorithm, arguments)
        runner = processing.runAndLoadResults if load_output else processing.run
        result = runner(algorithm.id(), prepared)
        return {
            "algorithm_id": algorithm.id(),
            "loaded_to_project": load_output,
            "parameters_used": prepared,
            "outputs": normalize_output(result),
        }
