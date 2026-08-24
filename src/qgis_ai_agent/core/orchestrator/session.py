from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionState:
    """Состояние диалога и планирования в рамках текущей сессии UI."""

    active_mode: str = "chat"
    pending_plan: dict[str, Any] | None = None
    pending_clarification: dict[str, Any] | None = None
    stream_message_id: int | None = None
    plan_message_id: int | None = None
    last_error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
