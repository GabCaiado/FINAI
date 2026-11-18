"""Statement description cleaning: raw bank text -> stable, comparable key text."""

import re
import unicodedata

# Words that carry no merchant information. One place, so rules, memory and dedupe agree.
GENERIC_WORDS: frozenset[str] = frozenset({"COMPRA", "CARTAO", "DEBITO", "CREDITO", "PAGTO", "PAG"})
MIN_LONG_NUMBER_DIGITS = 4  # shorter runs are kept: "99 POP", "BLOCO 2"
MERCHANT_KEY_TOKENS = 3

# DD/MM, DD/MM/YY(YY), DD-MM-YY(YY) and YYYY-MM-DD. A bare "7-11" is NOT a date: it is kept.
_DATE = re.compile(
    r"(?<![\d/])"
    r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{1,2}-\d{1,2}-\d{2,4})"
    r"(?![\d/])"
)
_LONG_NUMBER = re.compile(rf"\d{{{MIN_LONG_NUMBER_DIGITS},}}")
_GENERIC = re.compile(r"\b(?:" + "|".join(sorted(GENERIC_WORDS)) + r")\b")
_SPACES = re.compile(r"\s+")
_TOKEN = re.compile(r"[A-Z0-9]+")


def clean(description: str) -> str:
    """NFKD -> ASCII -> uppercase; strip dates, long digit runs and generic words; collapse spaces.

    Removals are repeated until nothing changes: a removal can alter the boundaries the other
    patterns look at, and a fixed point is what makes ``clean(clean(x)) == clean(x)`` true by
    construction rather than by case analysis. Every change shortens the text, so it always ends.
    """
    current = ascii_upper(description)
    while True:
        reduced = _reduce(current)
        if reduced == current:
            return current
        current = reduced


def merchant_key(description_clean: str) -> str:
    """First significant tokens (letters/digits) of an already cleaned description."""
    return " ".join(_TOKEN.findall(description_clean)[:MERCHANT_KEY_TOKENS])


def ascii_upper(text: str) -> str:
    """Accent-free uppercase ASCII (NFKD, non-ASCII dropped)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii").upper()


def _reduce(text: str) -> str:
    without_dates = _DATE.sub(" ", text)
    without_numbers = _LONG_NUMBER.sub(" ", without_dates)
    without_generic = _GENERIC.sub(" ", without_numbers)
    return _SPACES.sub(" ", without_generic).strip()
