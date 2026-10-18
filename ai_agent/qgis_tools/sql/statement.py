"""Reading an SQL text before QGIS sees it: one read-only SELECT, its identifiers, no file or schema functions.

Pure Python on purpose. The virtual layer provider would quietly run only the
first of several statements, and SpatiaLite carries functions that read and
write files; a read tool runs without the user's confirmation, so both are
refused here, before any layer is built.
"""

import re
from dataclasses import dataclass

WORD = "word"
QUOTED = "quoted"
STRING = "string"
NUMBER = "number"
PUNCT = "punct"
# SQLite quotes identifiers three ways; the first two double their closing mark to escape it.
IDENTIFIER_QUOTES = {'"': '"', "`": "`", "[": "]"}
STRING_QUOTE = "'"
WORD_PATTERN = re.compile(r"[^\W\d][\w$]*")
NUMBER_PATTERN = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
ALLOWED_STARTS = frozenset({"SELECT", "WITH"})
# What can follow a WITH clause at the top level: only SELECT reads.
STATEMENT_WORDS = frozenset({"SELECT", "VALUES", "INSERT", "UPDATE", "DELETE", "REPLACE"})
READ_STATEMENT = "SELECT"
# Bare words that are grammar, never a table: a layer named like one is matched only in double quotes.
SQL_KEYWORDS = re.compile(
    r"ALL|AND|AS|ASC|BETWEEN|BY|CASE|CAST|CROSS|DESC|DISTINCT|ELSE|END|ESCAPE|EXCEPT|EXISTS|FROM|FULL|GLOB"
    r"|GROUP|HAVING|IN|INNER|INTERSECT|IS|ISNULL|JOIN|LEFT|LIKE|LIMIT|MATERIALIZED|NATURAL|NOT|NOTNULL|NULL"
    r"|OFFSET|ON|OR|ORDER|OUTER|OVER|PARTITION|RECURSIVE|REGEXP|RIGHT|SELECT|THEN|UNION|USING|VALUES|WHEN"
    r"|WHERE|WINDOW|WITH",
    re.IGNORECASE,
)
# Functions that touch files, load code or change the database or the session, by name or name prefix.
# CreateUUID() goes with them: a prefix rule that misses a writer is worse than one refused harmless call.
DENIED_FUNCTIONS = re.compile(
    r"load_extension|fts3_tokenizer|readfile|writefile|edit|sqlite_attach|sqlite_detach"
    r"|blobfromfile|blobtofile|xb_loadxml|xb_storexml|checkgeometries|sanitizegeometrycolumn"
    r"|removeduplicaterows|elementarygeometries|setdecimalprecision|proj_setdatabasepath|proj_guesssrid\w*"
    r"|(?:import|export|zipfile_|sqlproc_|storedproc_|storedvar_|rl2_|create|drop|init|discard|recover"
    r"|rename|register|unregister|update|invalidate|enable|disable|clone|gpkgcreate|gpkgadd|gpkginsert)\w*",
    re.IGNORECASE,
)
SUMMARY_CHARS = 80
# The one argument both tools share, worded once.
SQL_PARAM = {
    "name": "sql",
    "type": "string",
    "description": (
        'One SQLite/SpatiaLite SELECT. Tables are project layer names in double quotes ("districts"); '
        "each layer's geometry column is geometry."
    ),
    "required": True,
}
EMPTY_ERROR = 'sql is empty. Pass one SELECT statement, e.g. SELECT name FROM "districts".'
UNTERMINATED_ERROR = "The SQL has an unterminated {0} that opens at character {1}. Close it and call again."
MULTIPLE_ERROR = (
    "Only one statement can run, and this SQL goes on after ';'. Send a single SELECT; "
    "ask a second question with a second call."
)
NOT_SELECT_ERROR = (
    "Only a read-only SELECT (or WITH ... SELECT) can run here, not {0}. "
    "Layers change through the other skills: edit, fields, processing, project."
)
DENIED_ERROR = (
    "The function {0}() is not allowed here: it reads or writes files, or changes the database. "
    "Use plain SQLite and SpatiaLite functions over the project's layers."
)


@dataclass(frozen=True)
class Token:
    """One lexical unit; `text` is an identifier's or a string's value without its quotes."""

    kind: str
    text: str
    depth: int
    end: int


def checked_sql(raw: object) -> str:
    """The statement to run: one SELECT, without a trailing ';' or comment. Raises ValueError otherwise."""
    text = str(raw or "").strip()
    tokens = statement_tokens(text)
    first = tokens[0]
    if first.kind != WORD or first.text.upper() not in ALLOWED_STARTS:
        raise ValueError(NOT_SELECT_ERROR.format(_shown(first)))
    main = _main_statement(tokens)
    if main != READ_STATEMENT:
        raise ValueError(NOT_SELECT_ERROR.format(main or "a WITH clause without a SELECT"))
    for name in function_names(tokens):
        if DENIED_FUNCTIONS.fullmatch(name):
            raise ValueError(DENIED_ERROR.format(name))
    return text[: tokens[-1].end]


def statement_tokens(text: str) -> list[Token]:
    """The tokens of the single statement in `text`; a trailing ';' is dropped, anything after it refused."""
    tokens = tokenize(text)
    for position, token in enumerate(tokens):
        if _is(token, ";"):
            if any(not _is(rest, ";") for rest in tokens[position + 1 :]):
                raise ValueError(MULTIPLE_ERROR)
            tokens = tokens[:position]
            break
    if not tokens:
        raise ValueError(EMPTY_ERROR)
    return tokens


def tokenize(text: str) -> list[Token]:
    """Split SQL into tokens, skipping whitespace and comments and tracking parenthesis depth."""
    tokens: list[Token] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif text.startswith("--", index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
        elif text.startswith("/*", index):
            # SQLite lets an unclosed block comment run to the end of the text.
            close = text.find("*/", index + 2)
            index = len(text) if close < 0 else close + 2
        elif char == STRING_QUOTE:
            index = _quoted(tokens, text, index, STRING, STRING_QUOTE, depth)
        elif char in IDENTIFIER_QUOTES:
            index = _quoted(tokens, text, index, QUOTED, IDENTIFIER_QUOTES[char], depth)
        else:
            index, depth = _plain(tokens, text, index, depth)
    return tokens


def identifiers(tokens: list[Token]) -> list[str]:
    """Names that may be tables, in order and once each: no keywords, function names or `alias.column` columns."""
    found: list[str] = []
    for position, token in enumerate(tokens):
        if token.kind not in (WORD, QUOTED):
            continue
        following = tokens[position + 1] if position + 1 < len(tokens) else None
        preceding = tokens[position - 1] if position else None
        if (following is not None and _is(following, "(")) or (preceding is not None and _is(preceding, ".")):
            continue
        if token.kind == WORD and SQL_KEYWORDS.fullmatch(token.text):
            continue
        if token.text and token.text not in found:
            found.append(token.text)
    return found


def function_names(tokens: list[Token]) -> list[str]:
    """Every name called like a function: a word or a quoted name right before '('."""
    return [
        token.text
        for token, following in zip(tokens, tokens[1:], strict=False)
        if token.kind in (WORD, QUOTED) and _is(following, "(")
    ]


def short_sql(raw: object) -> str:
    """The SQL on one line for a person to recognise, cut to SUMMARY_CHARS characters."""
    text = " ".join(str(raw or "").split())
    return text if len(text) <= SUMMARY_CHARS else text[: SUMMARY_CHARS - 1].rstrip() + "…"


def _quoted(tokens: list[Token], text: str, start: int, kind: str, closing: str, depth: int) -> int:
    index = start + 1
    while True:
        index = text.find(closing, index)
        if index < 0:
            what = "string" if kind == STRING else "quoted name"
            raise ValueError(UNTERMINATED_ERROR.format(what, start + 1))
        # A doubled closing mark is an escaped one, except for [brackets], which have no escape.
        if closing != "]" and text.startswith(closing * 2, index):
            index += 2
            continue
        value = text[start + 1 : index]
        if closing != "]":
            value = value.replace(closing * 2, closing)
        tokens.append(Token(kind, value, depth, index + 1))
        return index + 1


def _plain(tokens: list[Token], text: str, index: int, depth: int) -> tuple[int, int]:
    word = WORD_PATTERN.match(text, index)
    if word:
        tokens.append(Token(WORD, word.group(), depth, word.end()))
        return word.end(), depth
    number = NUMBER_PATTERN.match(text, index)
    if number:
        tokens.append(Token(NUMBER, number.group(), depth, number.end()))
        return number.end(), depth
    char = text[index]
    if char == "(":
        tokens.append(Token(PUNCT, char, depth, index + 1))
        return index + 1, depth + 1
    if char == ")":
        depth = max(0, depth - 1)
    tokens.append(Token(PUNCT, char, depth, index + 1))
    return index + 1, depth


def _main_statement(tokens: list[Token]) -> str:
    """The statement keyword at the top level: the first word, or for WITH the one after its clause."""
    words = [token.text.upper() for token in tokens if token.kind == WORD and token.depth == 0]
    if words[0] != "WITH":
        return words[0]
    return next((word for word in words[1:] if word in STATEMENT_WORDS), "")


def _is(token: Token, mark: str) -> bool:
    return token.kind == PUNCT and token.text == mark


def _shown(token: Token) -> str:
    if token.kind == WORD:
        return token.text.upper()
    return f"'{token.text}'"
