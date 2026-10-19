from ai_agent.core.llm.turns import ModelTurn


class TokenBudget:
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

    def add(self, turn: ModelTurn) -> None:
        self.requests += 1
        incoming, outgoing = max(0, int(turn.input_tokens)), max(0, int(turn.output_tokens))
        self.prompt += incoming
        self.completion += outgoing
        self.spent += incoming + outgoing

    def snapshot(self) -> dict[str, int]:
        return {"prompt_tokens": self.prompt, "completion_tokens": self.completion, "requests": self.requests}

    @property
    def exhausted(self) -> bool:
        return bool(self.limit) and self.spent >= self.limit
