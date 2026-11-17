"""Renders a Statement as OFX v1 (SGML), OFX v2 (XML), CSV variants and PDF. Pure functions."""

from __future__ import annotations

import csv
import io
from datetime import date
from xml.sax.saxutils import escape

from synth_personas import Statement, Txn

OFX_V1_CHARSET = "8859-1"
OFX_V1_ENCODING = "latin-1"
BANK_ID = "0000"
ACCOUNT_ID = "000123-4"
PDF_ROWS_PER_PAGE = 42
PDF_FOOTER_PREFIX = "Pagina"
CSV_KNOWN_HEADER = ("data", "descricao", "valor")
CSV_DEBIT_CREDIT_HEADER = ("Data", "Histórico", "Débito", "Crédito")
CSV_UNKNOWN_HEADER = ("Dt. Lanç.", "Detalhe", "Montante")


def br_number(cents: int, *, currency: bool = False) -> str:
    """-123456 -> '-1.234,56'; with `currency` -> '-R$ 1.234,56'."""
    whole, frac = divmod(abs(cents), 100)
    body = f"{whole:,}".replace(",", ".") + f",{frac:02d}"
    sign = "-" if cents < 0 else ""
    return f"{sign}R$ {body}" if currency else f"{sign}{body}"


def _text_amount(stmt: Statement, txn: Txn) -> int:
    return -txn.amount_cents if stmt.inverted_in_text else txn.amount_cents


def _csv_text(rows: list[tuple[str, ...]]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";", lineterminator="\n").writerows(rows)
    return buffer.getvalue()


def render_csv(stmt: Statement, *, currency: bool = False) -> str:
    rows: list[tuple[str, ...]] = [CSV_KNOWN_HEADER]
    rows += [
        (f"{t.date:%d/%m/%Y}", t.description, br_number(_text_amount(stmt, t), currency=currency))
        for t in stmt.txns
    ]
    return _csv_text(rows)


def render_csv_unknown_header(stmt: Statement) -> str:
    rows: list[tuple[str, ...]] = [CSV_UNKNOWN_HEADER]
    rows += [(f"{t.date:%d/%m/%Y}", t.description, br_number(t.amount_cents)) for t in stmt.txns]
    return _csv_text(rows)


def render_csv_debit_credit(stmt: Statement) -> str:
    rows: list[tuple[str, ...]] = [CSV_DEBIT_CREDIT_HEADER]
    for t in stmt.txns:
        amount = br_number(abs(t.amount_cents))
        debit, credit = (amount, "") if t.amount_cents < 0 else ("", amount)
        rows.append((f"{t.date:%d/%m/%Y}", t.description, debit, credit))
    return _csv_text(rows)


def _ofx_amount(cents: int) -> str:
    whole, frac = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}{whole}.{frac:02d}"


def _ofx_stamp(day: date) -> str:
    return f"{day:%Y%m%d}000000"


def _ofx_leaf(tag: str, value: str, *, closed: bool) -> str:
    return f"<{tag}>{value}</{tag}>" if closed else f"<{tag}>{value}"


def _ofx_txn(txn: Txn, *, closed: bool) -> list[str]:
    kind = "CREDIT" if txn.amount_cents > 0 else "DEBIT"
    leaves = (
        ("TRNTYPE", kind),
        ("DTPOSTED", _ofx_stamp(txn.date)),
        ("TRNAMT", _ofx_amount(txn.amount_cents)),
        ("FITID", txn.fitid),
        ("MEMO", escape(txn.description)),
    )
    return ["<STMTTRN>", *(_ofx_leaf(t, v, closed=closed) for t, v in leaves), "</STMTTRN>"]


def _ofx_body(stmt: Statement, *, closed: bool) -> list[str]:
    def leaf(tag: str, value: str) -> str:
        return _ofx_leaf(tag, value, closed=closed)

    acct_type = "CREDITCARD" if stmt.kind == "card" else "CHECKING"
    lines = [
        "<OFX>",
        "<SIGNONMSGSRSV1><SONRS>",
        "<STATUS>" + leaf("CODE", "0") + leaf("SEVERITY", "INFO") + "</STATUS>",
        leaf("DTSERVER", _ofx_stamp(stmt.period_end)),
        leaf("LANGUAGE", "POR"),
        "</SONRS></SIGNONMSGSRSV1>",
        "<BANKMSGSRSV1><STMTTRNRS>",
        leaf("TRNUID", "1"),
        "<STATUS>" + leaf("CODE", "0") + leaf("SEVERITY", "INFO") + "</STATUS>",
        "<STMTRS>",
        leaf("CURDEF", "BRL"),
        "<BANKACCTFROM>"
        + leaf("BANKID", BANK_ID)
        + leaf("ACCTID", ACCOUNT_ID)
        + leaf("ACCTTYPE", acct_type)
        + "</BANKACCTFROM>",
        "<BANKTRANLIST>",
        leaf("DTSTART", _ofx_stamp(stmt.period_start)),
        leaf("DTEND", _ofx_stamp(stmt.period_end)),
    ]
    for txn in stmt.txns:
        lines += _ofx_txn(txn, closed=closed)
    lines += ["</BANKTRANLIST>", "</STMTRS>", "</STMTTRNRS></BANKMSGSRSV1>", "</OFX>"]
    return lines


def render_ofx_v1(stmt: Statement) -> bytes:
    header = [
        "OFXHEADER:100",
        "DATA:OFXSGML",
        "VERSION:102",
        "SECURITY:NONE",
        "ENCODING:USASCII",
        f"CHARSET:{OFX_V1_CHARSET}",
        "COMPRESSION:NONE",
        "OLDFILEUID:NONE",
        "NEWFILEUID:NONE",
        "",
    ]
    text = "\r\n".join([*header, *_ofx_body(stmt, closed=False)]) + "\r\n"
    return text.encode(OFX_V1_ENCODING)


def render_ofx_v2(stmt: Statement) -> bytes:
    prolog = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<?OFX OFXHEADER="200" VERSION="220" SECURITY="NONE" OLDFILEUID="NONE" NEWFILEUID="NONE"?>',
    ]
    return ("\n".join([*prolog, *_ofx_body(stmt, closed=True)]) + "\n").encode("utf-8")


def pdf_line(stmt: Statement, txn: Txn) -> str:
    """The single supported layout: `DD/MM/YYYY  DESCRIPTION  -1.234,56`."""
    return f"{txn.date:%d/%m/%Y}  {txn.description}  {br_number(_text_amount(stmt, txn))}"


def render_pdf(stmt: Statement) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4, invariant=1, pageCompression=0)
    canvas.setTitle(f"FINAI synthetic statement {stmt.name}")
    lines = [pdf_line(stmt, t) for t in stmt.txns]
    pages = [lines[i : i + PDF_ROWS_PER_PAGE] for i in range(0, len(lines), PDF_ROWS_PER_PAGE)]
    width, height = A4
    for number, page in enumerate(pages, start=1):
        canvas.setFont("Helvetica", 9)
        canvas.drawString(40, height - 40, f"EXTRATO SINTETICO {stmt.name} - DADOS FICTICIOS")
        for row, line in enumerate(page):
            canvas.drawString(40, height - 70 - row * 16, line)
        canvas.drawString(40, 30, f"{PDF_FOOTER_PREFIX} {number} de {len(pages)}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()
