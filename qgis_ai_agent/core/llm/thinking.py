OPEN_TAGS = ("<think>", "<thinking>", "<reasoning>")
CLOSE_TAGS = ("</think>", "</thinking>", "</reasoning>")


class ThinkSplitter:
    def __init__(self) -> None:
        self._pending = ""
        self._inside = False

    @property
    def inside(self) -> bool:
        return self._inside

    def feed(self, text: str) -> tuple[str, str]:
        self._pending += text or ""
        visible: list[str] = []
        thought: list[str] = []
        while True:
            tags = CLOSE_TAGS if self._inside else OPEN_TAGS
            sink = thought if self._inside else visible
            index, tag = _earliest(self._pending, tags)
            if tag:
                sink.append(self._pending[:index])
                self._pending = self._pending[index + len(tag) :]
                self._inside = not self._inside
                continue
            safe = len(self._pending) - _held_back(self._pending, tags)
            sink.append(self._pending[:safe])
            self._pending = self._pending[safe:]
            break
        return "".join(visible), "".join(thought)

    def flush(self) -> tuple[str, str]:
        rest = self._pending
        self._pending = ""
        return ("", rest) if self._inside else (rest, "")


def split_thinking(text: str) -> tuple[str, str]:
    splitter = ThinkSplitter()
    visible, thought = splitter.feed(text)
    tail_visible, tail_thought = splitter.flush()
    return visible + tail_visible, thought + tail_thought


def _earliest(text: str, tags: tuple[str, ...]) -> tuple[int, str]:
    best = -1
    found = ""
    for tag in tags:
        index = text.find(tag)
        if index >= 0 and (best < 0 or index < best):
            best = index
            found = tag
    return best, found


def _held_back(text: str, tags: tuple[str, ...]) -> int:
    longest = max(len(tag) for tag in tags)
    for size in range(min(longest - 1, len(text)), 0, -1):
        suffix = text[-size:]
        if any(tag.startswith(suffix) for tag in tags):
            return size
    return 0
