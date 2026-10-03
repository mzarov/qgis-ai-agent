from ai_agent.core.llm.transport import ModelTurn


class TokenBudget:
    """Tokens spent by one run against the limit from Settings; a limit of 0 means none.

    The prompt/completion split and the request count are kept for reporting
    (the live-model token ceilings); only `spent` is checked against the limit.
    """

    def __init__(self) -> None:
        self.spent = 0
        self.limit = 0
        self.prompt = 0
        self.completion = 0
        self.requests = 0

    def reset(self, limit: int) -> None:
        self.spent = 0
        self.limit = max(0, int(limit or 0))
        self.prompt = 0
        self.completion = 0
        self.requests = 0

    def add(self, turn: ModelTurn) -> bool:
        """Count one answered model request; True when the token total changed."""
        self.requests += 1
        incoming, outgoing = max(0, int(turn.input_tokens)), max(0, int(turn.output_tokens))
        if incoming + outgoing <= 0:
            return False
        self.prompt += incoming
        self.completion += outgoing
        self.spent += incoming + outgoing
        return True

    def snapshot(self) -> dict[str, int]:
        """Prompt tokens, completion tokens and answered requests counted since the last reset."""
        return {"prompt_tokens": self.prompt, "completion_tokens": self.completion, "requests": self.requests}

    @property
    def exhausted(self) -> bool:
        return bool(self.limit) and self.spent >= self.limit
