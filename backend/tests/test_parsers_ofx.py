"""B2b: ``parse_ofx`` (SGML v1, XML v2, bank and card, encodings, hostile files)."""

import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from app.errors import AppError
from app.parsers.ofx_parser import OfxResult, parse_ofx

MAX_ROWS = 100
SAMPLES = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "samples"


@dataclass
class Trn:
    amount: str | None = "-10.00"
    posted: str | None = "20260901000000"
    fitid: str | None = "F1"
    memo: str | None = "CAFE"
    name: str | None = None


def leaf(tag: str, value: str | None, v2: bool) -> str:
    if value is None:
        return ""
    return f"<{tag}>{value}</{tag}>" if v2 else f"<{tag}>{value}"


def transaction(trn: Trn, v2: bool) -> str:
    fields = [
        leaf("TRNTYPE", "OTHER", v2),
        leaf("DTPOSTED", trn.posted, v2),
        leaf("TRNAMT", trn.amount, v2),
        leaf("FITID", trn.fitid, v2),
        leaf("NAME", trn.name, v2),
        leaf("MEMO", trn.memo, v2),
    ]
    return "<STMTTRN>" + "".join(fields) + "</STMTTRN>"


def build_ofx(
    transactions: list[Trn],
    *,
    v2: bool = False,
    charset: str = "8859-1",
    card: bool = False,
    account_id: str | None = "000123-4567",
) -> str:
    acct_tag = "CCACCTFROM" if card else "BANKACCTFROM"
    account = f"<{acct_tag}>{leaf('ACCTID', account_id, v2)}</{acct_tag}>" if account_id else ""
    statement = "CCSTMTRS" if card else "STMTRS"
    wrapper = "CREDITCARDMSGSRSV1" if card else "BANKMSGSRSV1"
    inner = "CCSTMTTRNRS" if card else "STMTTRNRS"
    body = "".join(transaction(t, v2) for t in transactions)
    message = (
        f"<OFX><{wrapper}><{inner}><{statement}>{leaf('CURDEF', 'BRL', v2)}{account}"
        f"<BANKTRANLIST>{body}</BANKTRANLIST></{statement}></{inner}></{wrapper}></OFX>"
    )
    if v2:
        header = (
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            '<?OFX OFXHEADER="200" VERSION="220" SECURITY="NONE" '
            'OLDFILEUID="NONE" NEWFILEUID="NONE"?>\n'
        )
    else:
        header = (
            "OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nSECURITY:NONE\nENCODING:USASCII\n"
            f"CHARSET:{charset}\nCOMPRESSION:NONE\nOLDFILEUID:NONE\nNEWFILEUID:NONE\n\n"
        )
    return header + message


def parse(text: str, encoding: str = "utf-8", max_rows: int = MAX_ROWS) -> OfxResult:
    return parse_ofx(text.encode(encoding), max_rows)


def error_of(content: bytes, max_rows: int = MAX_ROWS) -> AppError:
    with pytest.raises(AppError) as caught:
        parse_ofx(content, max_rows)
    return caught.value


# ----- the formats -----


@pytest.mark.parametrize("v2", [False, True], ids=["sgml-v1", "xml-v2"])
def test_bank_statement_in_both_syntaxes(v2: bool) -> None:
    trns = [Trn("-34.70", "20260901000000", "A1", "IFOOD"), Trn("1234.56", "20260902", "A2", "PIX")]

    result = parse(build_ofx(trns, v2=v2))

    assert [(r.date, r.description_raw, r.amount_cents, r.external_id) for r in result.rows] == [
        (date(2026, 9, 1), "IFOOD", -3470, "A1"),
        (date(2026, 9, 2), "PIX", 123456, "A2"),
    ]


@pytest.mark.parametrize("v2", [False, True], ids=["sgml-v1", "xml-v2"])
def test_credit_card_statement_keeps_the_ofx_sign_convention(v2: bool) -> None:
    trns = [Trn("-25.30", fitid="C1", memo="RAPPI"), Trn("100.00", fitid="C2", memo="PAGAMENTO")]

    result = parse(build_ofx(trns, v2=v2, card=True, account_id="4111222233334444"))

    assert [r.amount_cents for r in result.rows] == [-2530, 10000]
    assert result.account_hint == "4444"


def test_account_hint_is_only_the_last_four_digits() -> None:
    result = parse(build_ofx([Trn()], account_id="000123-4567"))

    assert result.account_hint == "4567"
    assert "0001" not in (result.account_hint or "")


def test_account_hint_is_none_when_missing_or_ambiguous() -> None:
    assert parse(build_ofx([Trn()], account_id=None)).account_hint is None
    two = build_ofx([Trn()], account_id="1111").replace(
        "</BANKACCTFROM>", "</BANKACCTFROM><BANKACCTFROM><ACCTID>2222</BANKACCTFROM>"
    )
    assert parse(two).account_hint is None


# ----- fields -----


@pytest.mark.parametrize(
    ("amount", "cents"),
    [("-34.70", -3470), ("1234.5", 123450), ("-12,34", -1234), ("100", 10000), ("+5.00", 500)],
)
def test_trnamt_is_read_with_decimal(amount: str, cents: int) -> None:
    assert parse(build_ofx([Trn(amount=amount)])).rows[0].amount_cents == cents


@pytest.mark.parametrize(
    "amount", ["1.234", "abc", "", "1.234,56", "1.2.3", None, "99999999999.99"]
)
def test_unreadable_trnamt_makes_the_file_unsupported(amount: str | None) -> None:
    assert error_of(build_ofx([Trn(amount=amount)]).encode()).code == "unsupported_file"


@pytest.mark.parametrize(
    "posted",
    [
        "20260901",
        "20260901000000",
        "20260901120000.000",
        "20260901120000[-3:BRT]",
        "20260901[0:GMT]",
    ],
)
def test_dtposted_is_the_calendar_date_as_written(posted: str) -> None:
    assert parse(build_ofx([Trn(posted=posted)])).rows[0].date == date(2026, 9, 1)


@pytest.mark.parametrize("posted", ["2026-09-01", "20261301", "202609", "", None, "01092026"])
def test_unreadable_dtposted_makes_the_file_unsupported(posted: str | None) -> None:
    assert error_of(build_ofx([Trn(posted=posted)]).encode()).code == "unsupported_file"


@pytest.mark.parametrize(
    ("memo", "name", "expected"),
    [
        ("DETALHE", None, "DETALHE"),
        (None, "ROTULO", "ROTULO"),
        ("DETALHE", "ROTULO", "ROTULO DETALHE"),
        ("IGUAL", "IGUAL", "IGUAL"),
        ("A &amp; B", None, "A & B"),
        ("AT&T", None, "AT&T"),
        ("&amp;lt;", None, "&lt;"),
        ("  espaco  ", None, "espaco"),
    ],
)
def test_description_comes_from_memo_and_or_name(
    memo: str | None, name: str | None, expected: str
) -> None:
    assert parse(build_ofx([Trn(memo=memo, name=name)])).rows[0].description_raw == expected


def test_a_transaction_without_memo_or_name_makes_the_file_unsupported() -> None:
    assert error_of(build_ofx([Trn(memo=None, name=None)]).encode()).code == "unsupported_file"


def test_zero_amount_transactions_are_skipped() -> None:
    result = parse(build_ofx([Trn("0.00", fitid="Z"), Trn("-1.00", fitid="N")]))

    assert [r.external_id for r in result.rows] == ["N"]


def test_a_file_with_only_zero_amounts_is_unsupported() -> None:
    assert error_of(build_ofx([Trn("0.00")]).encode()).code == "unsupported_file"


def test_missing_fitid_leaves_external_id_empty() -> None:
    assert parse(build_ofx([Trn(fitid=None)])).rows[0].external_id is None


def test_repeated_fitids_are_dropped_so_the_unique_constraint_cannot_break() -> None:
    trns = [Trn(fitid="X", memo="A"), Trn(fitid="X", memo="B"), Trn(fitid="Y", memo="C")]

    ids = [r.external_id for r in parse(build_ofx(trns)).rows]

    assert ids == [None, None, "Y"]


# ----- encodings -----


@pytest.mark.parametrize(
    ("charset", "encoding"),
    [("1252", "cp1252"), ("8859-1", "latin-1"), ("ISO-8859-1", "latin-1"), ("NONE", "utf-8")],
)
def test_declared_charset_decodes_accents(charset: str, encoding: str) -> None:
    text = build_ofx([Trn(memo="IMPRESSÕES AÇAÍ")], charset=charset)

    assert parse(text, encoding).rows[0].description_raw == "IMPRESSÕES AÇAÍ"


def test_cp1252_only_characters_survive() -> None:
    text = build_ofx([Trn(memo="CAFÉ – CENTRO")], charset="1252")

    assert parse(text, "cp1252").rows[0].description_raw == "CAFÉ – CENTRO"


def test_a_file_that_lies_about_its_charset_is_still_read_by_its_bytes() -> None:
    text = build_ofx([Trn(memo="AÇAÍ")], charset="1252")

    assert parse(text, "utf-8").rows[0].description_raw == "AÇAÍ"


def test_utf8_bom_is_tolerated() -> None:
    assert parse(build_ofx([Trn()], v2=True), "utf-8-sig").rows[0].amount_cents == -1000


# ----- limits -----


def test_max_rows_is_inclusive() -> None:
    trns = [Trn(fitid=f"F{i}") for i in range(3)]

    assert len(parse_ofx(build_ofx(trns).encode(), 3).rows) == 3


def test_more_transactions_than_the_limit_is_too_many_rows() -> None:
    trns = [Trn(fitid=f"F{i}") for i in range(4)]

    error = error_of(build_ofx(trns).encode(), max_rows=3)

    assert (error.code, error.status_code, error.details) == ("too_many_rows", 422, {"max_rows": 3})


# ----- unusable and hostile input -----


def test_investment_statements_are_not_read() -> None:
    text = build_ofx([Trn()]).replace("STMTRS", "INVSTMTRS").replace("BANKTRANLIST", "INVTRANLIST")

    assert error_of(text.encode()).code == "unsupported_file"


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   \n",
        b"data;descricao;valor\n01/09/2026;CAFE;-1,00",
        b"%PDF-1.4\x00\x01\x02",
        b"OFXHEADER:100\nDATA:OFXSGML\n",
        b"<OFX></OFX>",
        b"\xff\xfe<\x00O\x00F\x00X\x00>\x00",
    ],
)
def test_files_that_are_not_ofx_are_unsupported(content: bytes) -> None:
    error = error_of(content)

    assert (error.code, error.status_code) == ("unsupported_file", 422)


def test_a_statement_without_transactions_is_unsupported() -> None:
    assert error_of(build_ofx([]).encode()).code == "unsupported_file"


def test_a_truncated_file_is_unsupported_or_loses_nothing_silently() -> None:
    full = build_ofx([Trn(fitid=f"F{i}", memo=f"ITEM {i}") for i in range(5)]).encode()

    for cut in (len(full) // 3, len(full) // 2, len(full) - 40):
        try:
            result = parse_ofx(full[:cut], MAX_ROWS)
        except AppError as error:
            assert error.code == "unsupported_file"
        else:
            assert len(result.rows) <= 5


BILLION_LAUGHS = (
    '<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
)
EXTERNAL_ENTITY = '<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'


@pytest.mark.parametrize("declaration", [BILLION_LAUGHS, EXTERNAL_ENTITY, "<!doctype x>"])
def test_documents_declaring_entities_or_a_doctype_are_rejected(declaration: str) -> None:
    text = build_ofx([Trn(memo="&lol3;")], v2=True).replace("<OFX>", declaration + "\n<OFX>", 1)

    error = error_of(text.encode())

    assert error.code == "unsupported_file"
    assert "lol" not in json.dumps([error.message, error.details])


def test_the_same_declaration_in_sgml_is_rejected_too() -> None:
    text = build_ofx([Trn()]).replace("<OFX>", EXTERNAL_ENTITY + "<OFX>", 1)

    assert error_of(text.encode()).code == "unsupported_file"


def test_errors_never_contain_text_from_the_file() -> None:
    error = error_of(build_ofx([Trn(amount="SEGREDO-ABC", memo="SEGREDO-DEF")]).encode())

    assert "SEGREDO" not in json.dumps([error.message, error.details, str(error)])


@pytest.mark.parametrize("name", ["persona_a.ofx", "persona_b_v2.ofx", "persona_c.ofx"])
def test_random_corruption_only_ever_yields_a_result_or_a_domain_error(name: str) -> None:
    original = (SAMPLES / name).read_bytes()
    rng = random.Random(f"ofx-fuzz-{name}")

    for _ in range(150):
        data = bytearray(original)
        for _ in range(rng.randint(1, 8)):
            if not data:
                break
            position = rng.randrange(len(data))
            action = rng.choice(["flip", "delete", "truncate", "insert"])
            if action == "flip":
                data[position] = rng.randrange(256)
            elif action == "delete":
                del data[position : position + rng.randint(1, 30)]
            elif action == "insert":
                data[position:position] = rng.choice([b"<", b">", b"</", b"&", b"<A>", b"\n"])
            else:
                del data[position:]
        try:
            parse_ofx(bytes(data), MAX_ROWS)
        except AppError as error:
            assert error.code in {"unsupported_file", "too_many_rows"}
