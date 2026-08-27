import struct

MAGIC = bytes.fromhex("3cb86418caef9c95cd211cbf60a1bddd")
BLOCK_LANGUAGE = 0xA7
BLOCK_HASHES = 0x42
BLOCK_MESSAGES = 0x69
BLOCK_NUMERUS_RULES = 0x88
TAG_END = 0x01
TAG_TRANSLATION = 0x03
TAG_SOURCE_TEXT = 0x06
TAG_CONTEXT = 0x07
TAG_COMMENT = 0x08

Q_EQ = 0x01
Q_BETWEEN = 0x04
Q_NOT = 0x08
Q_MOD_10 = 0x10
Q_MOD_100 = 0x20
Q_AND = 0xFD
Q_NEWRULE = 0xFF

NUMERUS_RULES = {
    "en": bytes([Q_EQ, 1]),
    "ru": bytes(
        [
            Q_MOD_10 | Q_EQ,
            1,
            Q_AND,
            Q_MOD_100 | Q_NOT | Q_EQ,
            11,
            Q_NEWRULE,
            Q_MOD_10 | Q_BETWEEN,
            2,
            4,
            Q_AND,
            Q_MOD_100 | Q_NOT | Q_BETWEEN,
            10,
            19,
        ]
    ),
}
HASH_MASK = 0xFFFFFFFF
HIGH_NIBBLE = 0xF0000000


def elf_hash(text: str) -> int:
    value = 0
    for byte in text.encode("utf-8"):
        value = ((value << 4) + byte) & HASH_MASK
        carry = value & HIGH_NIBBLE
        if carry:
            value ^= carry >> 24
        value &= ~carry & HASH_MASK
    return value or 1


def compile_qm(language: str, messages: list[tuple[str, str, list[str]]]) -> bytes:
    if language not in NUMERUS_RULES:
        raise ValueError(f"no plural rules for '{language}': add them to NUMERUS_RULES")
    body = bytearray()
    index: list[tuple[int, int]] = []
    for context, source, forms in sorted(messages, key=lambda message: message[1]):
        index.append((elf_hash(source), len(body)))
        for form in forms:
            body += _item(TAG_TRANSLATION, form.encode("utf-16-be"))
        body += _item(TAG_COMMENT, b"")
        body += _item(TAG_SOURCE_TEXT, source.encode("utf-8"))
        body += _item(TAG_CONTEXT, context.encode("utf-8"))
        body.append(TAG_END)
    hashes = b"".join(struct.pack(">II", key, offset) for key, offset in sorted(index))
    return MAGIC + b"".join(
        (
            _block(BLOCK_LANGUAGE, language.encode("utf-8")),
            _block(BLOCK_HASHES, hashes),
            _block(BLOCK_MESSAGES, bytes(body)),
            _block(BLOCK_NUMERUS_RULES, NUMERUS_RULES[language]),
        )
    )


def _item(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + struct.pack(">I", len(payload)) + payload


def _block(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + struct.pack(">I", len(payload)) + payload


def read_qm(data: bytes) -> list[tuple[str, str, list[str]]]:
    blocks = {}
    position = len(MAGIC)
    while position < len(data):
        tag = data[position]
        size = struct.unpack(">I", data[position + 1 : position + 5])[0]
        blocks[tag] = data[position + 5 : position + 5 + size]
        position += 5 + size
    return _records(blocks.get(BLOCK_MESSAGES, b""))


def _records(body: bytes) -> list[tuple[str, str, list[str]]]:
    found: list[tuple[str, str, list[str]]] = []
    position = 0
    while position < len(body):
        context = source = ""
        forms: list[str] = []
        while position < len(body):
            tag = body[position]
            position += 1
            if tag == TAG_END:
                break
            size = struct.unpack(">I", body[position : position + 4])[0]
            position += 4
            payload = body[position : position + size]
            position += size
            if tag == TAG_TRANSLATION:
                forms.append(payload.decode("utf-16-be"))
            elif tag == TAG_SOURCE_TEXT:
                source = payload.decode("utf-8")
            elif tag == TAG_CONTEXT:
                context = payload.decode("utf-8")
        found.append((context, source, forms))
    return found
