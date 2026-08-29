import re

EXACT = 1000
WORD_HIT = 20
PART_OF_NAME = 6
IN_IDENTIFIER = 5
TAG_HIT = 3
GROUP_HIT = 1
MIN_STEM = 4
LENGTH_PENALTY_STEP = 10
MAX_PENALTY_LENGTH = 60
WORD_PATTERN = re.compile(r"[a-z0-9]+")


def score(haystack: dict[str, str], terms: list[str], query: str) -> int:
    if _is_exact(haystack, query):
        return EXACT
    name_words = _words(haystack["name"])
    tag_words = _words(haystack["tags"])
    total = 0
    for term in terms:
        total += _term_score(term, haystack, name_words, tag_words)
    if not total:
        return 0
    return max(1, total - _length_penalty(haystack["name"]))


def _term_score(term: str, haystack: dict[str, str], name_words: set, tag_words: set) -> int:
    total = 0
    if _hits(term, name_words):
        total += WORD_HIT
    elif term in haystack["name"]:
        total += PART_OF_NAME
    if term in haystack["bare"]:
        total += IN_IDENTIFIER
    if _hits(term, tag_words):
        total += TAG_HIT
    if term in haystack["group"]:
        total += GROUP_HIT
    return total


def _is_exact(haystack: dict[str, str], query: str) -> bool:
    return haystack["name"] == query or haystack["bare"] == query.replace(" ", "")


def _hits(term: str, bag: set) -> bool:
    if term in bag:
        return True
    return any(word.startswith(term) or (len(word) >= MIN_STEM and term.startswith(word)) for word in bag)


def _words(text: str) -> set:
    return set(WORD_PATTERN.findall(text))


def _length_penalty(name: str) -> int:
    return min(len(name), MAX_PENALTY_LENGTH) // LENGTH_PENALTY_STEP
