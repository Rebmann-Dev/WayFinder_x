from typing import List

from models.chat import ChatMessage


def build_chat_messages(
    messages: List[ChatMessage], max_history: int = 8
) -> list[dict[str, str]]:
    system_message = messages[0]
    recent_messages = messages[1:][-max_history:]

    return [system_message.to_dict()] + [msg.to_dict() for msg in recent_messages]
