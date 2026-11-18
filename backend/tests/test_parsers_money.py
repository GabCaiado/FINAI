"""B2: ``to_cents`` turns Brazilian money text into integer cents, and refuses ambiguity."""

import pytest

from app.parsers.money import MAX_ABS_CENTS, MoneyFormatError, to_cents


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # plain Brazilian formats
        ("1.234,56", 123_456),
        ("1234,56", 123_456),
        ("0,05", 5),
        ("99,9", 9_990),
        ("1.234.567,89", 123_456_789),
        ("1234", 123_400),
        ("0", 0),
        # currency symbol, whitespace, case
        ("R$ 1.234,56", 123_456),
        ("r$1.234,56", 123_456),
        ("  R$ 1.000,00  ", 100_000),
        ("1 234,56", 123_456),
        # negative markers
        ("-1.234,56", -123_456),
        ("-R$ 1.234,56", -123_456),
        ("R$ -1,00", -100),
        ("(1.234,56)", -123_456),
        ("(R$ 10,00)", -1_000),
        ("123,45-", -12_345),
        ("+10,00", 1_000),
        # the LAST separator is the decimal one when both appear
        ("1,234.56", 123_456),
        # only a comma: decimal
        ("12,5", 1_250),
        # only a dot: decimal with 1-2 digits after a single dot, otherwise thousands
        ("12.5", 1_250),
        ("12.50", 1_250),
        ("1234.56", 123_456),
        ("1.234", 123_400),
        ("12.345", 1_234_500),
        ("1.234.567", 123_456_700),
        # the largest amount that still fits an INTEGER column
        ("21.474.836,47", MAX_ABS_CENTS),
    ],
)
def test_to_cents_reads_each_documented_format(text: str, expected: int) -> None:
    result = to_cents(text)

    assert result == expected
    assert type(result) is int


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "R$",
        "abc",
        "-",
        "()",
        "1e5",
        "--1,00",
        "-(1,00)",
        "-1,00-",
        "(1,00",
        "1,00)",
        "12,34,56",  # a comma twice is not a decimal
        "1,234",  # three decimals: never rounded, never guessed as thousands
        "1.234,567",
        "1,00.5.6",
        "12.34.56",  # dots as thousands need groups of three
        "1234.567",  # one dot, three digits, but a four-digit leading group
        "0.123",  # a leading "0" group is not a thousands group
        "1..234",
        ".5",
        ",50",
        "5.",
        "21.474.836,48",  # one cent above the INTEGER range
        "9" * 40,
    ],
)
def test_to_cents_rejects_noise_and_ambiguity(text: str) -> None:
    with pytest.raises(MoneyFormatError):
        to_cents(text)


def test_money_error_is_a_value_error_and_never_echoes_the_input() -> None:
    with pytest.raises(ValueError) as caught:
        to_cents("zz-4242-secret")

    assert "4242" not in str(caught.value)
    assert "secret" not in str(caught.value)
