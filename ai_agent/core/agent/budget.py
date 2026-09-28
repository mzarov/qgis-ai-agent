from ai_agent.core.llm.transport import ModelTurn


class TokenBudget:
    """Tokens spent by one run against the limit from Settings; a limit of 0 means none."""

    def __init__(self) -> None:
        self.spent = 0
        self.limit = 0

    def reset(self, limit: int) -> None:
        self.spent = 0
        self.limit = max(0, int(limit or 0))

    def add(self, turn: ModelTurn) -> bool:
        """Count a turn's tokens; True when the total changed."""
        spent = int(turn.input_tokens) + int(turn.output_tokens)
        if spent <= 0:
            return False
        self.spent += spent
        return True

    @property
    def exhausted(self) -> bool:
        return bool(self.limit) and self.spent >= self.limit
