"""Bytes -> text for text-based statements (CSV, OFX)."""

from app.parsers.failures import unsupported_file

STRICT_ENCODINGS = ("utf-8-sig", "cp1252")
FALLBACK_ENCODING = "latin-1"  # decodes any byte sequence, so it is always the last resort


def decode_text(content: bytes) -> str:
    """Decode as UTF-8 (BOM allowed), else cp1252, else latin-1.

    Banks often declare one encoding and write another, so the bytes decide, not the header.
    Text containing NUL is binary data (PDF, UTF-16...) and raises ``unsupported_file``.
    """
    for encoding in STRICT_ENCODINGS:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        break
    else:
        text = content.decode(FALLBACK_ENCODING)
    if "\x00" in text:
        raise unsupported_file()
    return text
