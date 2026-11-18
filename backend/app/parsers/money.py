"""Brazilian money text -> integer cents. Never uses ``float``."""

import re
from decimal import Decimal

CENTS_PER_UNIT = 100
MAX_AMOUNT_TEXT_LENGTH = 32  # longer text is never a plausible amount; also bounds the work done
MAX_DECIMAL_PLACES = 2
MAX_ABS_CENTS = 2**31 - 1  # fits the INTEGER column of Postgres, so the insert cannot overflow
THOUSANDS_GROUP_LENGTH = 3
MAX_LEADING_GROUP_LENGTH = 3

_CURRENCY_SYMBOL = re.compile(r"R\$", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")
_ALLOWED = re.compile(r"[0-9.,]+")


class MoneyFormatError(ValueError):
    """The text is not an unambiguous amount. The message never contains the input."""


def to_cents(text: str) -> int:
    """Convert an amount written in Brazilian style to integer cents.

    Rules (each one has a test):

    * ``R$`` and any whitespace (including non-breaking spaces) are ignored.
    * Negative when written ``-1.234,56``, ``(1.234,56)`` or ``1.234,56-``; ``+`` is allowed.
      Combining two sign markers (``-(1,00)``, ``-1,00-``) is an error.
    * With both ``.`` and ``,`` the LAST separator is the decimal one; the other must be a
      well-formed thousands separator (``1.234.567,89``, ``1,234.56``).
    * With only ``,`` it is the decimal separator and may appear once (``1234,56``).
    * With only ``.`` it is decimal only when exactly 1 or 2 digits follow a single dot
      (``12.5``); otherwise every dot is a thousands separator (``1.234``, ``1.234.567``).
    * More than 2 decimal places is an error: nothing is ever rounded (``1,234`` is rejected
      rather than guessed).
    * Magnitudes above ``MAX_ABS_CENTS`` are an error.
    * Empty text, noise and malformed grouping (``12.34.56``, ``1234.567``) raise
      :class:`MoneyFormatError`.
    """
    body, negative = _split_sign(_normalise(text))
    integer_digits, fraction_digits = _split_number(body)
    cents = Decimal(f"{integer_digits}.{fraction_digits or '0'}") * CENTS_PER_UNIT
    value = int(cents)
    if value > MAX_ABS_CENTS:
        raise MoneyFormatError("amount out of range")
    return -value if negative else value


def _normalise(text: str) -> str:
    if len(text) > MAX_AMOUNT_TEXT_LENGTH * 2:
        raise MoneyFormatError("amount text too long")
    stripped = _WHITESPACE.sub("", _CURRENCY_SYMBOL.sub("", text))
    if not stripped or len(stripped) > MAX_AMOUNT_TEXT_LENGTH:
        raise MoneyFormatError("empty or oversized amount")
    return stripped


def _split_sign(text: str) -> tuple[str, bool]:
    """Return the unsigned body and whether it was negative."""
    markers = 0
    negative = False
    if text.startswith(("-", "+")):
        negative = text[0] == "-"
        text, markers = text[1:], markers + 1
    if text.endswith(("-", "+")):
        negative = text[-1] == "-"
        text, markers = text[:-1], markers + 1
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text, markers = text[1:-1], markers + 1
    if markers > 1 or not _ALLOWED.fullmatch(text):
        raise MoneyFormatError("malformed amount")
    return text, negative


def _split_number(body: str) -> tuple[str, str]:
    """Return ``(integer_digits, fraction_digits)`` after resolving the separators."""
    has_dot, has_comma = "." in body, "," in body
    if has_dot and has_comma:
        decimal = "," if body.rfind(",") > body.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        return _join(body, decimal, thousands)
    if has_comma:
        return _join(body, ",", None)
    if has_dot and _is_decimal_dot(body):
        return _join(body, ".", None)
    return _join(body, None, ".")


def _is_decimal_dot(body: str) -> bool:
    integer_part, _, fraction = body.rpartition(".")
    return body.count(".") == 1 and 1 <= len(fraction) <= MAX_DECIMAL_PLACES and bool(integer_part)


def _join(body: str, decimal: str | None, thousands: str | None) -> tuple[str, str]:
    integer_text, fraction = body, ""
    if decimal is not None:
        if body.count(decimal) != 1:
            raise MoneyFormatError("ambiguous decimal separator")
        integer_text, fraction = body.split(decimal)
    if thousands is not None and thousands in integer_text:
        _check_thousands_groups(integer_text, thousands)
        integer_text = integer_text.replace(thousands, "")
    elif decimal is None and not integer_text.isdigit():
        raise MoneyFormatError("malformed amount")
    if not integer_text.isdigit() or (fraction and not fraction.isdigit()):
        raise MoneyFormatError("malformed amount")
    if len(fraction) > MAX_DECIMAL_PLACES:
        raise MoneyFormatError("too many decimal places")
    return integer_text, fraction


def _check_thousands_groups(integer_text: str, separator: str) -> None:
    first, *rest = integer_text.split(separator)
    leading_ok = 1 <= len(first) <= MAX_LEADING_GROUP_LENGTH and first.isdigit() and first != "0"
    rest_ok = all(len(g) == THOUSANDS_GROUP_LENGTH and g.isdigit() for g in rest)
    if not (leading_ok and rest_ok):
        raise MoneyFormatError("malformed thousands grouping")


_PLAIN_AMOUNT = re.compile(r"[+-]?\d+(?:[.,]\d{1,2})?", re.ASCII)


def plain_to_cents(text: str) -> int:
    """Convert a machine-formatted amount (OFX ``TRNAMT``) to integer cents.

    Unlike :func:`to_cents` there is no thousands separator to disambiguate: the format is an
    optional sign, digits and optionally ONE ``.`` or ``,`` followed by 1 or 2 digits
    (``-34.70``, ``1234.5``, ``-1234,56``, ``100``). ``1.234`` is an error here, not R$ 1.234,00.
    """
    value = text.strip()
    if len(value) > MAX_AMOUNT_TEXT_LENGTH or not _PLAIN_AMOUNT.fullmatch(value):
        raise MoneyFormatError("malformed amount")
    cents = int(Decimal(value.replace(",", ".")) * CENTS_PER_UNIT)
    if abs(cents) > MAX_ABS_CENTS:
        raise MoneyFormatError("amount out of range")
    return cents
