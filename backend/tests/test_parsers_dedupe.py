"""B2: occurrence-index dedupe hashes (ARCHITECTURE 10.3)."""

import hashlib
from datetime import date

from app.parsers.cleaning import clean
from app.parsers.dedupe import assign_dedupe_hashes
from app.parsers.types import ParsedRow

ACCOUNT = "acc-1"
DAY = date(2026, 9, 12)


def row(description: str = "IFOOD *PASTELARIA", cents: int = -1500, day: date = DAY) -> ParsedRow:
    return ParsedRow(day, description, cents)


def test_hash_follows_the_documented_formula() -> None:
    first = row("COMPRA 12/09 Pastelaria Café")

    (digest,) = assign_dedupe_hashes([first], ACCOUNT)

    text = f"{ACCOUNT}|2026-09-12|-1500|{clean(first.description_raw)}|0"
    assert digest == hashlib.sha256(text.encode()).hexdigest()


def test_two_identical_purchases_on_the_same_day_get_distinct_hashes() -> None:
    hashes = assign_dedupe_hashes([row(), row()], ACCOUNT)

    assert len(set(hashes)) == 2


def test_reprocessing_the_same_file_reproduces_the_same_hashes() -> None:
    rows = [row(), row(), row("UBER *TRIP", -1310), row()]

    assert assign_dedupe_hashes(rows, ACCOUNT) == assign_dedupe_hashes(list(rows), ACCOUNT)


def test_a_different_account_changes_every_hash() -> None:
    rows = [row(), row("UBER *TRIP", -1310)]

    first = assign_dedupe_hashes(rows, "acc-1")
    second = assign_dedupe_hashes(rows, "acc-2")

    assert set(first).isdisjoint(second)


def test_reordering_distinct_rows_does_not_change_their_hashes() -> None:
    uber, netflix, spotify = row("UBER *TRIP", -1310), row("NETFLIX", -3990), row("SPOTIFY", -2190)

    forward = assign_dedupe_hashes([uber, netflix, spotify], ACCOUNT)
    shuffled = assign_dedupe_hashes([spotify, uber, netflix], ACCOUNT)

    assert shuffled == [forward[2], forward[0], forward[1]]


def test_each_field_of_the_key_changes_the_hash() -> None:
    base = assign_dedupe_hashes([row()], ACCOUNT)[0]
    variants = [row(day=date(2026, 9, 13)), row(cents=-1501), row("OUTRO LUGAR")]

    for variant in variants:
        assert assign_dedupe_hashes([variant], ACCOUNT)[0] != base


def test_descriptions_that_clean_to_the_same_text_are_the_same_purchase() -> None:
    plain = assign_dedupe_hashes([row("IFOOD")], ACCOUNT)
    noisy = assign_dedupe_hashes([row("COMPRA DEBITO IFOOD 12/09 998877")], ACCOUNT)

    assert plain == noisy


def test_the_occurrence_index_counts_per_key_not_per_file() -> None:
    coffee, bus = row("CAFE", -800), row("ONIBUS", -450)

    hashes = assign_dedupe_hashes([coffee, bus, coffee, bus, coffee], ACCOUNT)

    assert len(set(hashes)) == 5
    assert hashes[0] == assign_dedupe_hashes([coffee], ACCOUNT)[0]
    assert hashes[1] == assign_dedupe_hashes([bus], ACCOUNT)[0]


def test_empty_input_gives_no_hashes() -> None:
    assert assign_dedupe_hashes([], ACCOUNT) == []
