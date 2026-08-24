from qgis_ai_agent.core.chat.prompts import build_chat_system_prompt


class ConversationService:
    """Формирует сообщения для обычного диалога без выполнения тулов."""

    def build_messages(
        self,
        prompt: str,
        project_context: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": build_chat_system_prompt(project_context)},
        ]
        if history:
            messages.extend(history[-8:])
        messages.append({"role": "user", "content": prompt})
        return messages
