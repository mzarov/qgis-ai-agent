import re

ANNOUNCE_MAX_CHARS = 280
QUESTION_MARKS = ("?", "？")
ANNOUNCING = re.compile(
    r"\b(i'll|i will|i'm going to|i am going to|let me(?! know)|now i|next,? i|first,? i)\b", re.IGNORECASE
)


def announces_a_step(text: str) -> bool:
    flat = " ".join((text or "").split())
    if not flat or len(flat) > ANNOUNCE_MAX_CHARS or any(mark in flat for mark in QUESTION_MARKS):
        return False
    return ANNOUNCING.search(flat) is not None
