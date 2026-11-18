"""OFX (v1 SGML and v2 XML, bank and credit-card statements) -> canonical rows.

Only ``ofxtools``'s tolerant tree parser is used. Its ``convert()`` layer enforces the whole OFX
spec (for example a mandatory ``LEDGERBAL``) and would reject files banks actually send, and its
header check rejects the standard ``CHARSET:8859-1``. So the bytes are decoded here
(``text.decode_text``) and the declared charset is neutralised before the library sees them.

Security: ``ofxtools`` parses with its own regex tokenizer, not an XML parser, so it never expands
entities (no XXE, no billion laughs). Documents that declare a DOCTYPE or ENTITY are rejected
anyway, so the guarantee does not depend on the library staying that way.

Error messages never contain file content.
"""

import io
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from xml.etree.ElementTree import Element
from xml.sax.saxutils import unescape

from ofxtools.Parser import OFXTree

from app.parsers.failures import too_many_rows, unsupported_file
from app.parsers.money import plain_to_cents
from app.parsers.text import decode_text
from app.parsers.types import ParsedRow

STATEMENT_TAGS = frozenset({"STMTRS", "CCSTMTRS"})  # bank and credit-card statements
ACCOUNT_TAGS = frozenset({"BANKACCTFROM", "CCACCTFROM"})
ACCOUNT_HINT_DIGITS = 4
DESCRIPTION_SEPARATOR = " "
XML_ENTITIES = {"&quot;": '"', "&apos;": "'"}  # &amp; &lt; &gt; are handled by saxutils

# A parser failure of any kind means "not a usable OFX file": ofxtools raises SyntaxError
# subclasses (header, tokenizer) and ValueError subclasses (types, values, decoding).
PARSE_FAILURES = (SyntaxError, ValueError, KeyError, IndexError, AttributeError)

_DECLARATION = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)
_CHARSET_FIELD = re.compile(r"CHARSET:\s*[\w-]+")
_POSTED = re.compile(r"(\d{4})(\d{2})(\d{2})(?:\d{6}(?:\.\d{1,3})?)?(?:\[[^\]]*\])?", re.ASCII)


@dataclass(frozen=True, slots=True)
class OfxResult:
    """``account_hint`` is the last 4 digits of ``ACCTID`` when the file has exactly one account."""

    rows: list[ParsedRow]
    account_hint: str | None


def parse_ofx(content: bytes, max_rows: int) -> OfxResult:
    """Parse an OFX statement.

    ``TRNAMT`` is read with ``Decimal`` (``plain_to_cents``); ``DTPOSTED`` is the calendar date as
    written (time and time zone are ignored); the description is ``MEMO``, ``NAME`` or both when
    they differ; ``external_id`` is ``FITID``, dropped for every row whose ``FITID`` is repeated in
    the file (banks that reuse ids would otherwise break the per-account UNIQUE constraint, and
    those rows fall back to the occurrence-index hash). Zero-amount rows are skipped.
    Anything that is not a readable OFX with at least one transaction raises
    ``unsupported_file``; more than ``max_rows`` transactions raises ``too_many_rows``.
    """
    if _DECLARATION.search(content):
        raise unsupported_file()
    root = _build_tree(_with_neutral_charset(decode_text(content)))
    statements = [element for element in root.iter() if element.tag in STATEMENT_TAGS]
    rows = _collect_rows(statements, max_rows)
    if not rows:
        raise unsupported_file()
    return OfxResult(_without_repeated_ids(rows), _account_hint(statements))


def _with_neutral_charset(text: str) -> bytes:
    """Re-encode as UTF-8 and tell the library so: the bytes were already decoded correctly."""
    header_end = text.find("<")
    if header_end < 0:
        raise unsupported_file()
    header = _CHARSET_FIELD.sub("CHARSET:NONE", text[:header_end], count=1)
    return (header + text[header_end:]).encode("utf-8")


def _build_tree(data: bytes) -> Element:
    try:
        tree = OFXTree()
        tree.parse(io.BytesIO(data))
        root = tree.getroot()
    except PARSE_FAILURES:
        raise unsupported_file() from None
    if root is None:
        raise unsupported_file()
    return root


def _collect_rows(statements: list[Element], max_rows: int) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    seen = 0
    for statement in statements:
        for node in statement.iter("STMTTRN"):
            seen += 1
            if seen > max_rows:
                raise too_many_rows(max_rows)
            row = _to_row(node)
            if row.amount_cents != 0:  # the database stores no zero-amount row
                rows.append(row)
    return rows


def _to_row(node: Element) -> ParsedRow:
    try:
        posted = _parse_posted(node.findtext("DTPOSTED") or "")
        cents = plain_to_cents(node.findtext("TRNAMT") or "")
    except ValueError:
        raise unsupported_file() from None
    description = _description(node)
    if not description:
        raise unsupported_file()
    fitid = _text(node, "FITID")
    return ParsedRow(posted, description, cents, external_id=fitid or None)


def _parse_posted(text: str) -> date:
    match = _POSTED.fullmatch(text.strip())
    if match is None:
        raise ValueError("unsupported DTPOSTED")
    year, month, day = (int(part) for part in match.groups())
    return date(year, month, day)


def _text(node: Element, tag: str) -> str:
    return unescape(node.findtext(tag) or "", XML_ENTITIES).strip()


def _description(node: Element) -> str:
    memo, name = _text(node, "MEMO"), _text(node, "NAME")
    parts = [part for part in (name, memo) if part]
    if len(parts) == 2 and parts[0] == parts[1]:
        parts = parts[:1]
    return DESCRIPTION_SEPARATOR.join(parts)


def _without_repeated_ids(rows: list[ParsedRow]) -> list[ParsedRow]:
    counts = Counter(row.external_id for row in rows if row.external_id is not None)
    return [
        replace(row, external_id=None) if row.external_id and counts[row.external_id] > 1 else row
        for row in rows
    ]


def _account_hint(statements: list[Element]) -> str | None:
    """Last digits of the account id, never the whole number; ``None`` if absent or ambiguous."""
    ids: set[str] = set()
    for statement in statements:
        for element in statement.iter():
            if element.tag in ACCOUNT_TAGS:
                digits = re.sub(r"\D", "", element.findtext("ACCTID") or "")
                if digits:
                    ids.add(digits)
    if len(ids) != 1:
        return None
    return ids.pop()[-ACCOUNT_HINT_DIGITS:]
