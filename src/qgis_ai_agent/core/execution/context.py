from dataclasses import dataclass


@dataclass
class StepContext:
    """Контекст исполнения шагов, расширяемый для будущих доменов."""

    layout_name: str | None = None
