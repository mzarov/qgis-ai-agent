from typing import Any

IMAGE_URL_BLOCK = "image_url"
IMAGE_REJECTED_STATUS_CODES = (400, 413, 415, 422)
IMAGE_STRIPPED_NOTE = "[image omitted: this endpoint rejected image input]"


def has_images(messages: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(block, dict) and block.get("type") == IMAGE_URL_BLOCK
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
    )


def without_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            cleaned.append(message)
            continue
        parts = [
            str(block.get("text") or "") if block.get("type") != IMAGE_URL_BLOCK else IMAGE_STRIPPED_NOTE
            for block in content
            if isinstance(block, dict)
        ]
        cleaned.append({**message, "content": "\n".join(part for part in parts if part)})
    return cleaned
