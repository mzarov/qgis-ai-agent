import base64
import struct
import zlib
from typing import Any

from ai_agent.core.llm.client import BLOCKING_TIMEOUT_FACTOR
from ai_agent.i18n import tr

PROBE_PROMPT = "Reply with one word: ok"
REPLY_LIMIT = 160
PROBE_SECONDS = 60
EMPTY_REPLY = tr("Connected, but the model returned an empty answer.")
IMAGE_PROMPT = "Name the two colours of this picture, left half first. Reply with the two colour names only."
# Green and yellow, not red and blue: a model that never got the picture guesses the common pair.
PROBE_COLOURS = (("green", (0, 160, 0)), ("yellow", (255, 255, 0)))
PROBE_SIZE = (128, 64)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_RGB = 2


def probe(overrides: dict[str, Any]) -> tuple[bool, str]:
    from ai_agent.core.llm.transport import call_model

    try:
        turn = call_model(
            [{"role": "user", "content": PROBE_PROMPT}],
            [],
            overrides=overrides,
            timeout=PROBE_SECONDS // BLOCKING_TIMEOUT_FACTOR,
        )
    except Exception as error:
        return False, _shortened(str(error) or type(error).__name__)
    reply = turn.text
    if not reply.strip():
        return False, EMPTY_REPLY
    return True, tr("Model replied: {0}").format(_shortened(reply))


def sees_images(overrides: dict[str, Any]) -> bool | None:
    """Whether the model reads a picture, judged by its answer about one; None when the request failed.

    An endpoint may take an image and drop it before the model, which then says it sees none or
    guesses. Only naming both colours counts. An endpoint that refuses the image outright is retried
    without it by the transport, so that answer names no colour either.
    """
    from ai_agent.core.llm.transport import call_model

    picture = base64.b64encode(two_halves_png(PROBE_SIZE, *(rgb for _, rgb in PROBE_COLOURS))).decode("ascii")
    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": IMAGE_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{picture}"}},
        ],
    }
    try:
        turn = call_model([message], [], overrides=overrides, timeout=PROBE_SECONDS // BLOCKING_TIMEOUT_FACTOR)
    except Exception:
        return None
    reply = turn.text.casefold()
    return all(name in reply for name, _ in PROBE_COLOURS)


def two_halves_png(size: tuple[int, int], left: tuple[int, int, int], right: tuple[int, int, int]) -> bytes:
    """A PNG whose left half is one colour and right half another, built without Qt: the probe runs off the main
    thread."""
    width, height = size
    row = b"\x00" + bytes(left) * (width // 2) + bytes(right) * (width - width // 2)
    header = struct.pack(">IIBBBBB", width, height, 8, PNG_RGB, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(row * height)) + _chunk(b"IEND", b"")


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _shortened(text: str) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= REPLY_LIMIT else flat[:REPLY_LIMIT] + "…"
