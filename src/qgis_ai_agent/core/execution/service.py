from qgis_ai_agent.core.execution.context import StepContext
from qgis_ai_agent.qgis_tools.registry import execute_step


class ExecutionService:
    """Выполнение плана шагов через реестр тулов."""

    def execute_steps(self, steps: list[dict]) -> str | None:
        context = StepContext()
        for step in steps:
            tool = step.get("tool")
            params = dict(step.get("params") or {})
            params.setdefault("layout_name", context.layout_name or "Макет ИИ")
            result = execute_step(tool, params)
            context.layout_name = result.get("layout_name", context.layout_name)
        return context.layout_name
