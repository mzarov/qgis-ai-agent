OPEN_TAGS = ("<think>", "<thinking>", "<reasoning>")
CLOSE_TAGS = ("</think>", "</thinking>", "</reasoning>")


class ThinkSplitter:
    def __init__(self, held: bool = False) -> None:
        self._pending = ""
        self._inside = False
        self._held = held
        self.closed_without_opening = False

    def feed(self, text: str) -> tuple[str, str]:
        self._pending += text or ""
        held_thought = self._release() if self._held else ""
        if self._held:
            return "", ""
        visible, thought = self._split()
        return visible, held_thought + thought

    def _release(self) -> str:
        close_index, close_tag = leading_close(self._pending)
        if close_tag:
            thought = self._pending[:close_index]
            self._pending = self._pending[close_index + len(close_tag) :]
            self._held = False
            self.closed_without_opening = True
            return thought
        if _earliest(self._pending, OPEN_TAGS)[1]:
            self._held = False
        return ""

    def _split(self) -> tuple[str, str]:
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
        self._held = False
        return ("", rest) if self._inside else (rest, "")


def leading_close(text: str) -> tuple[int, str]:
    close_index, close_tag = _earliest(text, CLOSE_TAGS)
    open_index, _ = _earliest(text, OPEN_TAGS)
    if close_tag and (open_index < 0 or close_index < open_index):
        return close_index, close_tag
    return -1, ""


def split_thinking(text: str) -> tuple[str, str]:
    text = text or ""
    close_index, close_tag = leading_close(text)
    if close_tag:
        visible, thought = split_thinking(text[close_index + len(close_tag) :])
        return visible, text[:close_index] + thought
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
