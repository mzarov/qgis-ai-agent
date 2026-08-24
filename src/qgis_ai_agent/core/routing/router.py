class IntentRouter:
    """Legacy router: stage selection is now model-driven in planning prompt."""

    def route(self, text: str) -> str:
        _ = text
        return "model_driven"
