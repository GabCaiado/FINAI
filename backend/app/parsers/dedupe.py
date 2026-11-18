"""Occurrence-index dedupe hashes (ARCHITECTURE 10.3). Pure: checking the database is B5's job."""

import hashlib
from collections import Counter
from collections.abc import Sequence

from app.parsers.cleaning import clean
from app.parsers.types import ParsedRow

HASH_SEPARATOR = "|"


def assign_dedupe_hashes(rows: Sequence[ParsedRow], account_id: str) -> list[str]:
    """One sha256 per row, in file order.

    ``n`` is the 0-based occurrence index of the row among the rows with the same
    ``(account, date, amount_cents, description_clean)``, counted in file order. Two identical
    coffees on the same day therefore get distinct hashes, and re-reading the same file gives
    the same hashes. Distinct rows never influence each other's ``n``, so reordering them is
    harmless.
    """
    seen: Counter[tuple[str, str, int, str]] = Counter()
    hashes: list[str] = []
    for row in rows:
        key = (account_id, row.date.isoformat(), row.amount_cents, clean(row.description_raw))
        hashes.append(_digest(key, seen[key]))
        seen[key] += 1
    return hashes


def _digest(key: tuple[str, str, int, str], occurrence: int) -> str:
    text = HASH_SEPARATOR.join([*(str(part) for part in key), str(occurrence)])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
