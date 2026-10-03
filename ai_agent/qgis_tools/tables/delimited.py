"""Reading a delimited text file the way the QGIS delimitedtext provider will.

Pure Python on purpose: `prepare` checks a file before anything touches QGIS,
and the same code runs in tests without it. Only a bounded head of the file is
read, so a preview of a gigabyte export costs the same as one of a small table.
"""

import codecs
import csv
import difflib
import io
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import url2pathname

TABLE_SUFFIXES = (".csv", ".tsv", ".txt")
DELIMITERS = (",", ";", "\t", "|")
TAB = "tab"
SAMPLE_BYTES = 256 * 1024
SCAN_BYTES = 20 * 1024 * 1024
SNIFF_LINES = 20
UTF8 = "UTF-8"
UTF16 = "UTF-16"
UTF16_BOMS = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
CYRILLIC_ENCODING = "windows-1251"
WESTERN_ENCODING = "windows-1252"
# A text that is mostly Cyrillic letters once decoded as windows-1251 was
# written in it; anything else not in UTF-8 is taken for a Western export.
CYRILLIC_SHARE = 0.3
TEXT = "text"
INTEGER = "integer"
DOUBLE = "double"
BOOLEAN = "bool"
# The provider's boolean literals: a column using one pair only is typed bool.
BOOLEAN_PAIRS = (("true", "false"), ("t", "f"), ("yes", "no"), ("1", "0"))
INTEGER_PATTERN = re.compile(r"[+-]?\d+")
REAL_PATTERN = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
COMMA_REAL_PATTERN = re.compile(r"[+-]?\d+,\d+")
LEADING_ZERO_PATTERN = re.compile(r"[+-]?0\d+")
MAX_LISTED_COLUMNS = 40
CLOSE_MATCH_CUTOFF = 0.6


@dataclass(frozen=True)
class DelimitedTable:
    """The header and the first rows of a delimited text file."""

    path: str
    delimiter: str
    encoding: str
    header: list[str]
    rows: list[list[str]]
    complete: bool
    # Whether numbers are written as 37,5 — the provider needs decimalPoint=, then.
    # A field, not a property: number() runs once per coordinate value.
    decimal_comma: bool = False

    @property
    def delimiter_name(self) -> str:
        return TAB if self.delimiter == "\t" else self.delimiter

    @property
    def stem(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0] or "table"

    def values(self, column: str, strip: bool = True) -> list[str]:
        """The non-blank sampled values of one column; QGIS itself keeps the spaces of text."""
        index = self.header.index(column)
        found = [row[index] for row in self.rows if index < len(row) and row[index].strip()]
        return [value.strip() for value in found] if strip else found

    def column_type(self, column: str) -> str:
        """The type QGIS will detect, except that codes with leading zeros stay text."""
        return column_type(self.values(column), self.decimal_comma)

    def text_codes(self) -> list[str]:
        """Columns of digit codes like 007 that type detection would turn into numbers."""
        return [column for column in self.header if has_leading_zeros(self.values(column))]

    def number(self, value: str) -> float | None:
        return parse_number(value, self.decimal_comma)

    def require_columns(self, names: list[str]) -> None:
        missing = [name for name in names if name not in self.header]
        if missing:
            raise ValueError(
                f"'{os.path.basename(self.path)}' has no column {', '.join(repr(n) for n in missing)}. "
                f"{column_hint(missing, self.header)}"
            )


def read_table(path: str, delimiter: str = "", limit: int = SAMPLE_BYTES) -> DelimitedTable:
    """Read the header and up to `limit` bytes of rows; errors name what to fix."""
    clean = checked_path(path)
    with open(clean, "rb") as handle:
        raw = handle.read(limit + 1)
    complete = len(raw) <= limit
    text, encoding = _decode(raw[:limit], complete)
    if not complete:
        text = text[: text.rfind("\n") + 1] or text
    if "\0" in text:
        raise ValueError(f"'{clean}' is a binary file, not delimited text. Export it from its program as CSV.")
    chosen = _wanted_delimiter(delimiter)
    try:
        chosen = chosen or _sniff(text)
        rows = [row for row in csv.reader(io.StringIO(text), delimiter=chosen) if any(cell.strip() for cell in row)]
    except csv.Error as error:
        raise ValueError(
            f"'{clean}' could not be split into columns ({error}). An unclosed quote or a wrong delimiter "
            "makes one huge cell; check the file or pass delimiter."
        ) from None
    if not rows:
        raise ValueError(f"'{clean}' is empty: there is no header row.")
    header = field_names(rows[0])
    return DelimitedTable(clean, chosen, encoding, header, rows[1:], complete, _decimal_comma(header, rows[1:]))


def field_names(cells: list[str]) -> list[str]:
    """Header cells named as the provider names them: trimmed, field_N when empty, a_1 for a repeat."""
    names: list[str] = []
    for position, cell in enumerate(cells, start=1):
        base = cell.strip() or f"field_{position}"
        name, repeat = base, 0
        while name in names:
            repeat += 1
            name = f"{base}_{repeat}"
        names.append(name)
    return names


def checked_path(path: str) -> str:
    clean = os.path.expanduser(str(path or "").strip())
    if clean.lower().startswith("file:"):
        clean = url2pathname(urlparse(clean).path)
    if not clean:
        raise ValueError("No file path was given.")
    if not clean.lower().endswith(TABLE_SUFFIXES):
        raise ValueError(
            f"'{clean}' is not a delimited text file ({', '.join(TABLE_SUFFIXES)}). "
            "Load other formats with add_layer from the project skill."
        )
    if not os.path.isfile(clean):
        raise ValueError(f"There is no file '{clean}' on disk. Check the path.")
    return os.path.abspath(clean)


def looks_like_file(text: str) -> bool:
    """Whether a table argument names a file rather than a project layer."""
    clean = str(text or "").strip()
    if not clean.lower().endswith(TABLE_SUFFIXES):
        return False
    return os.sep in clean or "/" in clean or os.path.isfile(os.path.expanduser(clean))


def column_type(values: list[str], decimal_comma: bool = False) -> str:
    if not values or has_leading_zeros(values):
        return TEXT
    if boolean_pair(values):
        return BOOLEAN
    if all(INTEGER_PATTERN.fullmatch(value) for value in values):
        return INTEGER
    if all(parse_number(value, decimal_comma) is not None for value in values):
        return DOUBLE
    return TEXT


def boolean_pair(values: list[str]) -> tuple[str, str] | None:
    lowered = {value.lower() for value in values}
    return next((pair for pair in BOOLEAN_PAIRS if lowered <= set(pair)), None)


def has_leading_zeros(values: list[str]) -> bool:
    return any(LEADING_ZERO_PATTERN.fullmatch(value) for value in values) and all(
        INTEGER_PATTERN.fullmatch(value) for value in values
    )


def parse_number(value: str, decimal_comma: bool = False) -> float | None:
    text = value.strip()
    if decimal_comma:
        text = text.replace(",", ".", 1) if COMMA_REAL_PATTERN.fullmatch(text) else text
    if not REAL_PATTERN.fullmatch(text):
        return None
    return float(text)


def column_hint(missing: list[str], available: list[str]) -> str:
    close: list[str] = []
    for name in missing:
        close.extend(difflib.get_close_matches(name, available, n=3, cutoff=CLOSE_MATCH_CUTOFF))
    shown = ", ".join(available[:MAX_LISTED_COLUMNS])
    more = f" (and {len(available) - MAX_LISTED_COLUMNS} more)" if len(available) > MAX_LISTED_COLUMNS else ""
    similar = f"Similar: {', '.join(dict.fromkeys(close))}. " if close else ""
    return f"{similar}Available columns: {shown}{more}."


def _wanted_delimiter(raw: str) -> str:
    text = str(raw or "")
    if not text:
        return ""
    if text.strip().lower() in (TAB, "\\t", "\t"):
        return "\t"
    if text not in DELIMITERS:
        raise ValueError(f"Unsupported delimiter {text!r}. Use one of: , ; tab |")
    return text


def _sniff(text: str) -> str:
    """The delimiter that splits the first lines into the most, consistently wide columns."""
    lines = text.splitlines()[:SNIFF_LINES]
    best, best_width = DELIMITERS[0], 1
    for candidate in DELIMITERS:
        widths = [len(row) for row in csv.reader(lines, delimiter=candidate) if row]
        if not widths or widths[0] <= 1:
            continue
        consistent = sum(1 for width in widths if width == widths[0]) >= max(1, len(widths) * 0.8)
        if consistent and widths[0] > best_width:
            best, best_width = candidate, widths[0]
    return best


def _decimal_comma(header: list[str], rows: list[list[str]]) -> bool:
    for index in range(len(header)):
        values = [row[index].strip() for row in rows if index < len(row) and row[index].strip()]
        commas = any(COMMA_REAL_PATTERN.fullmatch(value) for value in values)
        if commas and all(COMMA_REAL_PATTERN.fullmatch(v) or INTEGER_PATTERN.fullmatch(v) for v in values):
            return True
    return False


def _decode(raw: bytes, complete: bool) -> tuple[str, str]:
    if raw.startswith(UTF16_BOMS):
        # Excel's "Unicode text" export; the provider reads it as UTF-16 once told so.
        return codecs.getincrementaldecoder("utf-16")(errors="replace").decode(raw, final=complete), UTF16
    try:
        # Incremental, so a sample cut inside a multi-byte letter is not mistaken for another encoding.
        return codecs.getincrementaldecoder("utf-8-sig")().decode(raw, final=complete), UTF8
    except UnicodeDecodeError:
        pass
    text = raw.decode(CYRILLIC_ENCODING, errors="replace")
    letters = [char for char in text if char.isalpha()]
    cyrillic = [char for char in letters if "\u0400" <= char <= "\u04ff"]
    if letters and len(cyrillic) / len(letters) >= CYRILLIC_SHARE:
        return text, CYRILLIC_ENCODING
    return raw.decode(WESTERN_ENCODING, errors="replace"), WESTERN_ENCODING
