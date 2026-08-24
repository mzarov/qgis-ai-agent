from qgis_ai_agent.core.planning.clarification import (
    apply_clarification_answer,
    build_clarification_questions,
)
from qgis_ai_agent.core.planning.parser import parse_model_json
from qgis_ai_agent.core.planning.prompts import build_planning_system_prompt
from qgis_ai_agent.qgis_tools.registry import validate_plan_steps


class PlanService:
    """Формирует prompt планирования и парсит ответ модели в структуру плана."""

    def build_messages(
        self,
        prompt: str,
        project_context: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": build_planning_system_prompt(project_context)},
        ]
        if history:
            messages.extend(history[-8:])
        messages.append({"role": "user", "content": prompt})
        return messages

    def parse_response(self, reply: str) -> dict:
        data = parse_model_json(reply)
        next_stage = (data.get("next_stage") or "").strip().lower()
        if not next_stage:
            next_stage = "plan" if data.get("can_do", True) else "chat"
            data["next_stage"] = next_stage

        if next_stage == "chat":
            data.setdefault("can_do", False)
            data.setdefault("steps", [])
            return data
        if next_stage == "execute":
            data.setdefault("can_do", True)
            data.setdefault("steps", [])
            return data

        steps = data.get("steps") or []
        errors = validate_plan_steps(steps)
        if errors:
            data["can_do"] = False
            data["message"] = "План содержит ошибки: " + "; ".join(errors)
            data["steps"] = []
            data["next_stage"] = "chat"
            return data

        clarification_questions = data.get("clarification_questions")
        if not clarification_questions:
            clarification_questions = build_clarification_questions(steps)
            if clarification_questions:
                data["clarification_questions"] = clarification_questions
        return data

    def apply_clarification_answer(self, data: dict, answer: str) -> dict:
        return apply_clarification_answer(data, answer)
