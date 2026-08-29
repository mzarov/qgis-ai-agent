from html.parser import HTMLParser

BLOCK_TAGS = {"article", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "section", "table", "tr"}
DROP_TAGS = {"head", "noscript", "script", "style", "svg"}


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.dropped: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if self.dropped:
            if lowered in DROP_TAGS:
                self.dropped.append(lowered)
            return
        if lowered in DROP_TAGS:
            self.dropped.append(lowered)
        elif lowered in BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if not self.dropped and tag.lower() in BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self.dropped:
            if lowered == self.dropped[-1]:
                self.dropped.pop()
            return
        if lowered in BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.dropped:
            self.chunks.append(data)


def normalize_text(value: str) -> str:
    lines = []
    for line in str(value or "").splitlines():
        compact = " ".join(line.split())
        if compact:
            lines.append(compact)
    return "\n".join(lines)


def html_to_text(html: str) -> str:
    parser = TextParser()
    parser.feed(str(html or ""))
    parser.close()
    return normalize_text("".join(parser.chunks))
