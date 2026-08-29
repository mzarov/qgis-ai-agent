from typing import Any


def conversation_scope(conversation: Any) -> tuple[str, str]:
    return conversation.project_key, conversation.session_identifier
