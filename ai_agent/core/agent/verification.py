from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent.prompts import build_verification_prompt
from ai_agent.core.agent.request import detect_images_unsupported
from ai_agent.core.agent.transcript import ToolResult

LOG_TAG = "AI Agent"
MAX_VERIFICATION_ROUNDS = 3


@dataclass
class VerificationStart:
    prompt: str
    round: int
    preload: list[str] = field(default_factory=list)


def plan_verification(
    results: Sequence[ToolResult],
    current_round: int,
    request: str,
    loaded_skills: list[str],
    overrides: dict[str, Any] | None = None,
) -> VerificationStart | None:
    next_round = current_round + 1
    if next_round > MAX_VERIFICATION_ROUNDS:
        QgsMessageLog.logMessage(
            f"Stopping after {MAX_VERIFICATION_ROUNDS} verification rounds.", LOG_TAG, Qgis.MessageLevel.Warning
        )
        return None
    outcomes: list[dict[str, Any]] = [
        {"tool": result.call.name, "ok": result.ok, "error": result.error} for result in results
    ]
    prompt = build_verification_prompt(outcomes, request, images=not detect_images_unsupported(overrides))
    return VerificationStart(prompt, next_round, list(loaded_skills))
