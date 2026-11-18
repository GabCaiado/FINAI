"""B2: ``parse_csv`` (delimiters, encodings, mapping, sign, limits, error hygiene)."""

import json
from datetime import date

import pytest
from pydantic import ValidationError

from app.errors import AppError
from app.parsers.csv_parser import MAX_REPORTED_LINES, CsvMapping, parse_csv
from app.parsers.types import ParsedRow

MAX_ROWS = 100


def csv_bytes(*lines: str, encoding: str = "utf-8", newline: str = "\n") -> bytes:
    return newline.join(lines).encode(encoding)


def parse(
    content: bytes, mapping: CsvMapping | None = None, invert: bool = False
) -> list[ParsedRow]:
    return parse_csv(content, mapping, invert, MAX_ROWS)


def error_of(
    content: bytes, mapping: CsvMapping | None = None, max_rows: int = MAX_ROWS
) -> AppError:
    with pytest.raises(AppError) as caught:
        parse_csv(content, mapping, False, max_rows)
    return caught.value


def test_semicolon_csv_with_brazilian_numbers() -> None:
    rows = parse(
        csv_bytes("data;descricao;valor", "01/09/2026;IFOOD;-34,70", "02/09/2026;PIX;1.234,56")
    )

    assert rows == [
        ParsedRow(date(2026, 9, 1), "IFOOD", -3470),
        ParsedRow(date(2026, 9, 2), "PIX", 123456),
    ]


def test_comma_csv_needs_quotes_around_decimal_commas() -> None:
    rows = parse(csv_bytes("Data,Descricao,Valor", '03/09/2026,"LOJA, CENTRO","-1.234,56"'))

    assert rows == [ParsedRow(date(2026, 9, 3), "LOJA, CENTRO", -123456)]


def test_tab_separated_csv() -> None:
    rows = parse(csv_bytes("data\tdescricao\tvalor", "03/09/2026\tCAFE\t-8,00"))

    assert rows == [ParsedRow(date(2026, 9, 3), "CAFE", -800)]


def test_currency_prefix_and_negative_with_prefix() -> None:
    rows = parse(
        csv_bytes(
            "data;descricao;valor",
            "02/09/2026;RECEBIDO;R$ 4.058,80",
            "03/09/2026;COWORKING;-R$ 450,00",
        )
    )

    assert [r.amount_cents for r in rows] == [405880, -45000]


def test_debit_and_credit_columns_use_credit_minus_debit() -> None:
    rows = parse(
        csv_bytes(
            "Data;Histórico;Débito;Crédito",
            "02/09/2026;GIRAFFAS;41,90;",
            "03/09/2026;SALARIO;;3.000,00",
        )
    )

    assert [r.amount_cents for r in rows] == [-4190, 300000]


def test_invert_sign_flips_every_amount() -> None:
    content = csv_bytes(
        "data;descricao;valor", "02/09/2026;RAPPI;25,30", "09/09/2026;PAGAMENTO RECEBIDO;-100,00"
    )

    assert [r.amount_cents for r in parse(content, invert=True)] == [-2530, 10000]
    assert [r.amount_cents for r in parse(content)] == [2530, -10000]


def test_invert_sign_also_applies_to_debit_credit_columns() -> None:
    rows = parse(csv_bytes("data;historico;debito;credito", "02/09/2026;X;10,00;"), invert=True)

    assert rows[0].amount_cents == 1000


def test_latin1_file_keeps_its_accents() -> None:
    content = csv_bytes(
        "Data;Descrição;Valor", "01/09/2026;IMPRESSÕES XEROX;-12,00", encoding="latin-1"
    )

    assert parse(content)[0].description_raw == "IMPRESSÕES XEROX"


def test_cp1252_file_keeps_its_typographic_characters() -> None:
    content = csv_bytes(
        "Data;Descrição;Valor", "01/09/2026;CAFÉ – CENTRO;-12,00", encoding="cp1252"
    )

    assert parse(content)[0].description_raw == "CAFÉ – CENTRO"


def test_utf8_bom_is_not_part_of_the_first_header() -> None:
    content = csv_bytes("data;descricao;valor", "01/09/2026;CAFÉ;-12,00", encoding="utf-8-sig")

    assert parse(content) == [ParsedRow(date(2026, 9, 1), "CAFÉ", -1200)]


def test_crlf_blank_lines_and_trailing_newline_are_tolerated() -> None:
    content = csv_bytes("data;descricao;valor", "", "01/09/2026;CAFE;-1,00", "", "", newline="\r\n")

    assert len(parse(content)) == 1


def test_quoted_field_with_the_delimiter_inside() -> None:
    rows = parse(csv_bytes("data;descricao;valor", '01/09/2026;"LOJA; FILIAL 2";-1,00'))

    assert rows[0].description_raw == "LOJA; FILIAL 2"


# ----- mapping -----


def test_unknown_header_asks_for_a_mapping_and_lists_the_columns() -> None:
    error = error_of(csv_bytes("Dt. Lanç.;Detalhe;Montante", "01/09/2026;CAFE;-1,00"))

    assert (error.code, error.status_code) == ("mapping_required", 422)
    assert error.details == {"columns": ["Dt. Lanç.", "Detalhe", "Montante"]}


def test_explicit_mapping_reads_an_unknown_header() -> None:
    mapping = CsvMapping(date="Dt. Lanç.", description="Detalhe", amount="Montante")

    rows = parse(csv_bytes("Dt. Lanç.;Detalhe;Montante", "01/09/2026;CAFE;-1,00"), mapping)

    assert rows == [ParsedRow(date(2026, 9, 1), "CAFE", -100)]


def test_explicit_mapping_with_debit_and_credit() -> None:
    mapping = CsvMapping(date="D", description="H", debit="Saiu", credit="Entrou")

    rows = parse(
        csv_bytes("D;H;Saiu;Entrou", "01/09/2026;CAFE;5,00;", "02/09/2026;PIX;;7,00"), mapping
    )

    assert [r.amount_cents for r in rows] == [-500, 700]


def test_mapping_naming_a_missing_column_asks_again() -> None:
    mapping = CsvMapping(date="Data", description="Descricao", amount="Total")

    error = error_of(csv_bytes("Data;Descricao;Valor", "01/09/2026;CAFE;-1,00"), mapping)

    assert error.code == "mapping_required"
    assert error.details == {"columns": ["Data", "Descricao", "Valor"]}


@pytest.mark.parametrize(
    "header",
    [
        "data;descricao;valor;valor",  # two candidates for the same role
        "data;descricao;valor;debito;credito",  # amount and debit/credit together
        "data;descricao;debito",  # debit without credit
        "descricao;valor",  # no date
    ],
)
def test_ambiguous_or_incomplete_known_headers_ask_for_a_mapping(header: str) -> None:
    assert error_of(csv_bytes(header, "01/09/2026;CAFE;-1,00;1")).code == "mapping_required"


def test_mapping_requires_amount_or_both_debit_and_credit() -> None:
    for fields in [
        {"amount": "V", "debit": "D", "credit": "C"},
        {"debit": "D"},
        {"credit": "C"},
        {},
    ]:
        with pytest.raises(ValidationError):
            CsvMapping(date="Data", description="Desc", **fields)


def test_mapping_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CsvMapping(date="D", description="H", amount="V", invert=True)  # type: ignore[call-arg]


# ----- dates -----


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01/09/2026", date(2026, 9, 1)),
        ("1/9/2026", date(2026, 9, 1)),
        ("01/09/26", date(2026, 9, 1)),
        ("2026-09-01", date(2026, 9, 1)),
        (" 29/02/2028 ", date(2028, 2, 29)),
    ],
)
def test_explicit_date_formats(text: str, expected: date) -> None:
    rows = parse(csv_bytes("data;descricao;valor", f"{text};CAFE;-1,00"))

    assert rows[0].date == expected


@pytest.mark.parametrize(
    "text",
    [
        "31/02/2026",
        "13/13/2026",
        "29/02/2027",
        "09-12-2026",
        "2026/09/01",
        "01.09.2026",
        "1 set 2026",
        "",
        "2026-9-1",
    ],
)
def test_ambiguous_or_impossible_dates_are_invalid_rows(text: str) -> None:
    error = error_of(csv_bytes("data;descricao;valor", f"{text};CAFE;-1,00"))

    assert (error.code, error.status_code, error.details) == ("invalid_row", 422, {"lines": [2]})


# ----- invalid rows -----


def test_invalid_row_reports_line_numbers_and_never_echoes_content() -> None:
    content = csv_bytes(
        "data;descricao;valor",
        "01/09/2026;OK;-1,00",
        "",
        "99/99/2026;SEGREDO-ABC;-7,00",
        "02/09/2026;SEGREDO-DEF;abc",
        "03/09/2026;;-1,00",
        "05/09/2026;SEGREDO-JKL",
    )

    error = error_of(content)

    assert error.code == "invalid_row"
    assert error.details == {"lines": [4, 5, 6, 7]}
    leaked = json.dumps([error.message, error.details, str(error)])
    assert "SEGREDO" not in leaked
    assert "99/99" not in leaked


def test_zero_amount_rows_are_skipped_because_the_database_cannot_store_them() -> None:
    content = csv_bytes("data;descricao;valor", "01/09/2026;SALDO;0,00", "02/09/2026;CAFE;-1,00")

    assert parse(content) == [ParsedRow(date(2026, 9, 2), "CAFE", -100)]


def test_a_file_with_only_zero_amount_rows_is_unsupported() -> None:
    assert error_of(csv_bytes("data;descricao;valor", "01/09/2026;SALDO;0,00")).code == (
        "unsupported_file"
    )


def test_invalid_row_stops_after_the_maximum_number_of_reported_lines() -> None:
    bad = ["xx;CAFE;-1,00"] * (MAX_REPORTED_LINES + 3)

    error = error_of(csv_bytes("data;descricao;valor", *bad))

    assert error.details == {"lines": [2, 3, 4, 5, 6]}


def test_one_bad_row_rejects_the_whole_file() -> None:
    content = csv_bytes("data;descricao;valor", "01/09/2026;OK;-1,00", "01/09/2026;BAD;1,234")

    assert error_of(content).details == {"lines": [3]}


# ----- limits and unusable files -----


def test_max_rows_is_inclusive() -> None:
    lines = ["data;descricao;valor", *(f"01/09/2026;ITEM {i};-1,00" for i in range(3))]

    assert len(parse_csv(csv_bytes(*lines), None, False, 3)) == 3


def test_more_rows_than_the_limit_is_too_many_rows() -> None:
    lines = ["data;descricao;valor", *(f"01/09/2026;ITEM {i};-1,00" for i in range(4))]

    error = error_of(csv_bytes(*lines), max_rows=3)

    assert (error.code, error.status_code, error.details) == ("too_many_rows", 422, {"max_rows": 3})


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   \n\n  ",
        b"data;descricao;valor",
        b"data;descricao;valor\n\n",
        b"%PDF-1.4\x00\x01\x02",
        b"\xff\xfed\x00a\x00",
    ],
)
def test_empty_or_binary_files_are_unsupported(content: bytes) -> None:
    error = error_of(content)

    assert (error.code, error.status_code) == ("unsupported_file", 422)


def test_single_column_text_is_unsupported() -> None:
    assert error_of(csv_bytes("isto nao e um extrato", "nem isto")).code == "unsupported_file"


def test_field_larger_than_the_csv_limit_is_unsupported() -> None:
    huge = "x" * 200_000

    assert (
        error_of(csv_bytes("data;descricao;valor", f"01/09/2026;{huge};-1,00")).code
        == "unsupported_file"
    )
