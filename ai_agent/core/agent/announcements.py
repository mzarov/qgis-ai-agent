"""Telling a first reply that only announces its next step from a finished answer.

A model sometimes ends the first turn of a run with "This is an export, so I'll
load the export tool." and calls nothing. A reply without tool calls ends the
run, so nothing happens and the user is left with a promise. Such a reply is
short, says what is about to happen, and asks nothing. Only a run that has
called no tool yet is judged: after real work, "I'll save it if you like" is an
offer, which the prompt asks for. The source stays English, so only English
phrasing is recognised; a short plain answer ("Two layers.") never is.
"""

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
