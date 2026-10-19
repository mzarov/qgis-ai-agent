from ai_agent.core.state.conversation import ConversationState


def conversation_scope(conversation: ConversationState) -> tuple[str, str]:
    return conversation.project_key, conversation.session_identifier
