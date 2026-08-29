import re
from html import unescape

DROP_BLOCKS = re.compile(r"<(script|style|noscript|svg|head)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")
BLOCK_TAGS = re.compile(r"</?(p|div|br|li|tr|h[1-6]|section|article|table)[^>]*>", re.IGNORECASE)
BLANK_LINES = re.compile(r"\n\s*\n+")
SPACES = re.compile(r"[ \t]+")


def html_to_text(html: str) -> str:
    cleaned = DROP_BLOCKS.sub(" ", str(html or ""))
    cleaned = BLOCK_TAGS.sub("\n", cleaned)
    cleaned = TAG.sub(" ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = SPACES.sub(" ", cleaned)
    lines = [line.strip() for line in cleaned.split("\n")]
    return BLANK_LINES.sub("\n", "\n".join(line for line in lines if line)).strip()
