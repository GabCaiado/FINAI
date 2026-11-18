"""Generic bank CSV -> canonical rows. Stdlib ``csv`` in streaming mode, no pandas.

Error messages and ``details`` never contain text from the file's data rows (only the 1-based
physical line numbers of the first bad rows, and the header names for the mapping step).
"""

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app import messages
from app.errors import AppError
from app.parsers.cleaning import ascii_upper
from app.parsers.failures import UNPROCESSABLE, too_many_rows, unsupported_file
from app.parsers.money import to_cents
from app.parsers.text import decode_text
from app.parsers.types import ParsedRow

DELIMITERS = ";,\t"
MAX_REPORTED_LINES = 5
TWO_DIGIT_YEAR_BASE = 2000  # "DD/MM/YY" is always read as 20YY

# Header names (accent-free, uppercase) that map automatically to each role.
KNOWN_HEADERS: dict[str, frozenset[str]] = {
    "date": frozenset({"DATA"}),
    "description": frozenset({"DESCRICAO", "HISTORICO", "LANCAMENTO"}),
    "amount": frozenset({"VALOR"}),
    "debit": frozenset({"DEBITO"}),
    "credit": frozenset({"CREDITO"}),
}

_DMY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", re.ASCII)
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})", re.ASCII)
_SPACES = re.compile(r"\s+")


class CsvMapping(BaseModel):
    """Which header names hold each field: ``amount`` XOR (``debit`` and ``credit``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None

    @model_validator(mode="after")
    def _single_amount_source(self) -> Self:
        has_amount = self.amount is not None
        has_split = self.debit is not None and self.credit is not None
        has_partial_split = (self.debit is None) != (self.credit is None)
        if has_amount == has_split or has_partial_split:
            raise ValueError("use either amount or both debit and credit")
        return self


@dataclass(frozen=True, slots=True)
class _Columns:
    """Positions of the mapped columns in the header."""

    date: int
    description: int
    amount: int | None
    debit: int | None
    credit: int | None

    @property
    def widest(self) -> int:
        used = (self.date, self.description, self.amount, self.debit, self.credit)
        return max(i for i in used if i is not None)


def parse_csv(
    content: bytes, mapping: CsvMapping | None, invert_sign: bool, max_rows: int
) -> list[ParsedRow]:
    """Parse a statement CSV.

    Without ``mapping`` the header must use known names (``KNOWN_HEADERS``), otherwise
    ``mapping_required`` (422) lists the columns. Rows with an unreadable date or amount, or an
    empty description, raise ``invalid_row`` with up to ``MAX_REPORTED_LINES`` line numbers.
    Zero-amount rows are skipped (the database cannot store them and they carry no money).
    More than ``max_rows`` data rows raises ``too_many_rows``.
    ``invert_sign`` flips every amount (card statements that list purchases as positive).
    """
    text = decode_text(content)
    records = _records(text, _detect_delimiter(text))
    first = next(records, None)
    if first is None:
        raise unsupported_file()
    header = [cell.strip() for cell in first[1]]
    columns = _locate(header, mapping or _auto_mapping(header))
    rows = _read_rows(records, columns, invert_sign, max_rows)
    if not rows:
        raise unsupported_file()
    return rows


def _detect_delimiter(text: str) -> str:
    """Sniff the header line only: data lines contain decimal commas that mislead the sniffer."""
    header_line = next((line for line in text.splitlines() if line.strip()), "")
    try:
        return csv.Sniffer().sniff(header_line, delimiters=DELIMITERS).delimiter
    except csv.Error:
        raise unsupported_file() from None


def _records(text: str, delimiter: str) -> Iterator[tuple[int, list[str]]]:
    """Yield ``(line_number, cells)`` for every non-blank record."""
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        for record in reader:
            if any(cell.strip() for cell in record):
                yield reader.line_num, record
    except csv.Error:
        raise unsupported_file() from None


def _auto_mapping(header: list[str]) -> CsvMapping:
    folded = [_SPACES.sub(" ", ascii_upper(name)).strip() for name in header]
    found: dict[str, str] = {}
    for role, aliases in KNOWN_HEADERS.items():
        matches = [name for name, key in zip(header, folded, strict=True) if key in aliases]
        if len(matches) == 1:  # two candidates for one role is ambiguous: ask the user
            found[role] = matches[0]
    try:
        return CsvMapping(**found)
    except (ValidationError, TypeError):
        raise _mapping_required(header) from None


def _locate(header: list[str], mapping: CsvMapping) -> _Columns:
    def index_of(name: str | None) -> int | None:
        if name is None:
            return None
        if header.count(name) != 1:
            raise _mapping_required(header)
        return header.index(name)

    date_col = index_of(mapping.date)
    description_col = index_of(mapping.description)
    if date_col is None or description_col is None:
        raise _mapping_required(header)
    return _Columns(
        date_col,
        description_col,
        index_of(mapping.amount),
        index_of(mapping.debit),
        index_of(mapping.credit),
    )


def _read_rows(
    records: Iterator[tuple[int, list[str]]],
    columns: _Columns,
    invert_sign: bool,
    max_rows: int,
) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    bad_lines: list[int] = []
    for count, (line_number, record) in enumerate(records, start=1):
        if count > max_rows:
            raise too_many_rows(max_rows)
        try:
            row = _parse_record(record, columns, invert_sign)
        except ValueError:  # includes MoneyFormatError
            bad_lines.append(line_number)
            if len(bad_lines) == MAX_REPORTED_LINES:
                break
            continue
        if row.amount_cents != 0:  # the database stores no zero-amount row; it carries no money
            rows.append(row)
    if bad_lines:
        raise AppError(
            "invalid_row", messages.INVALID_ROW, UNPROCESSABLE, details={"lines": bad_lines}
        )
    return rows


def _parse_record(record: list[str], columns: _Columns, invert_sign: bool) -> ParsedRow:
    """Build the row or raise ``ValueError`` when a required field is unreadable."""
    if len(record) <= columns.widest:
        raise ValueError("short record")
    description = record[columns.description].strip()
    if not description:
        raise ValueError("empty description")
    cents = _amount_cents(record, columns)
    posted = _parse_date(record[columns.date])
    return ParsedRow(posted, description, -cents if invert_sign else cents)


def _amount_cents(record: list[str], columns: _Columns) -> int:
    if columns.amount is not None:
        return to_cents(record[columns.amount])
    assert columns.debit is not None and columns.credit is not None  # guaranteed by CsvMapping
    debit, credit = record[columns.debit].strip(), record[columns.credit].strip()
    if not debit and not credit:
        raise ValueError("no amount")
    return (to_cents(credit) if credit else 0) - (to_cents(debit) if debit else 0)


def _parse_date(text: str) -> date:
    """Only explicit formats: DD/MM/YYYY, DD/MM/YY and YYYY-MM-DD. Anything else is an error."""
    value = text.strip()
    if match := _DMY.fullmatch(value):
        day, month, year = (int(part) for part in match.groups())
        return date(year + TWO_DIGIT_YEAR_BASE if len(match[3]) == 2 else year, month, day)
    if match := _ISO.fullmatch(value):
        year, month, day = (int(part) for part in match.groups())
        return date(year, month, day)
    raise ValueError("unsupported date format")


def _mapping_required(header: list[str]) -> AppError:
    return AppError(
        "mapping_required",
        messages.MAPPING_REQUIRED,
        UNPROCESSABLE,
        details={"columns": header},
    )
