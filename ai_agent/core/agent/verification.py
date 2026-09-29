from dataclasses import dataclass, field
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.agent.prompts import build_verification_prompt

LOG_TAG = "AI Agent"
MAX_VERIFICATION_ROUNDS = 3


@dataclass
class VerificationStart:
    prompt: str
    round: int
    preload: list[str] = field(default_factory=list)


def plan_verification(
    results: list[Any], current_round: int, request: str, loaded_skills: list[str]
) -> VerificationStart | None:
    """What the check after Apply runs with, or None once the round cap is reached.

    It starts with the applying run's skills (no load_skill turn, the same
    cached prefix) and is told the user's original request, which a long run
    may already have pushed out of the history window.
    """
    next_round = current_round + 1
    if next_round > MAX_VERIFICATION_ROUNDS:
        QgsMessageLog.logMessage(
            f"Stopping after {MAX_VERIFICATION_ROUNDS} verification rounds.", LOG_TAG, Qgis.MessageLevel.Warning
        )
        return None
    outcomes = [
        {"tool": result.call.name, "ok": result.ok, "error": str(result.payload.get("error", ""))} for result in results
    ]
    return VerificationStart(build_verification_prompt(outcomes, request), next_round, list(loaded_skills))
