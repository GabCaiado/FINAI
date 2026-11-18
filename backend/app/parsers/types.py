"""Canonical row shared by every importer (OFX, CSV, PDF)."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ParsedRow:
    """One statement line, before cleaning, classification or persistence.

    ``amount_cents`` is signed: income > 0, expense < 0 (the sign is the only income/expense flag).
    ``external_id`` is the bank's own id (OFX ``FITID``): when present it is the primary dedupe key
    (``Transaction`` is UNIQUE on ``(account_id, external_id)``); B5 falls back to the occurrence
    hash from ``dedupe.assign_dedupe_hashes`` only when it is ``None``.
    """

    date: date
    description_raw: str
    amount_cents: int
    external_id: str | None = None
