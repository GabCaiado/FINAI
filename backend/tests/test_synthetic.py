"""P1.3: synthetic statements and golden set (determinism, twins, mandatory cases, distribution).

The generator lives outside the app package, so it is loaded by path. No network, no real data.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import sys
from collections import Counter
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from xml.sax.saxutils import unescape

import pdfplumber
import pytest

from app.categories import CATEGORIES, is_allowed
from app.errors import AppError
from app.parsers import csv_parser, ofx_parser

SYNTH_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
SAMPLES_DIR = SYNTH_DIR / "samples"
SEED = 1234
MAX_IMPORT_ROWS = 5000  # same as backend/.env.test
START_MONTH = "2026-03"

Row = tuple[date, str, int]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SYNTH_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generate = _load("generate")  # also puts SYNTH_DIR on sys.path for its sibling modules
kappa = _load("kappa")


@pytest.fixture(scope="module")
def out_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("synthetic")
    assert (
        generate.main(["--out", str(path), "--seed", str(SEED), "--start-month", START_MONTH]) == 0
    )
    return path


@pytest.fixture(scope="module")
def statements() -> dict[str, object]:
    built = generate.build_statements(SEED, generate.parse_month(START_MONTH))
    return {s.name: s for s in built}


# ----- parsing helpers (test-local; the real parsers arrive in B2/B2b/B3) -----


def br_to_cents(text: str) -> int:
    cleaned = text.replace("R$", "").replace(" ", "")
    negative = cleaned.startswith("-")
    value = Decimal(cleaned.lstrip("-").replace(".", "").replace(",", "."))
    return int(value * 100) * (-1 if negative else 1)


def _dmy(text: str) -> date:
    day, month, year = (int(x) for x in text.split("/"))
    return date(year, month, day)


def _ofx_field(block: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<\r\n]*)", block)
    assert match, tag
    return match.group(1)


def parse_ofx(data: bytes, encoding: str) -> list[Row]:
    rows = []
    for block in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", data.decode(encoding), re.S):
        stamp = _ofx_field(block, "DTPOSTED")
        posted = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        cents = int(Decimal(_ofx_field(block, "TRNAMT")) * 100)
        rows.append((posted, unescape(_ofx_field(block, "MEMO")), cents))
    return rows


def parse_csv(data: bytes) -> list[Row]:
    reader = csv.reader(io.StringIO(data.decode("utf-8")), delimiter=";")
    header = next(reader)
    rows = []
    for line in reader:
        if len(header) == 4:  # debit/credit variant
            cents = (br_to_cents(line[3]) if line[3] else 0) - (
                br_to_cents(line[2]) if line[2] else 0
            )
        else:
            cents = br_to_cents(line[2])
        rows.append((_dmy(line[0]), line[1], cents))
    return rows


PDF_LINE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?[\d.]+,\d{2})$")


def parse_pdf(data: bytes) -> list[Row]:
    rows = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                match = PDF_LINE.match(line)
                if match:
                    rows.append((_dmy(match[1]), match[2], br_to_cents(match[3])))
    return rows


def _expected(stmt: object) -> list[Row]:
    return [(t.date, t.description, t.amount_cents) for t in stmt.txns]  # type: ignore[attr-defined]


def _as_text_sign(stmt: object, rows: list[Row]) -> list[Row]:
    """Card CSV/PDF list purchases as positive numbers; undo that to compare with the model."""
    if not stmt.inverted_in_text:  # type: ignore[attr-defined]
        return rows
    return [(d, t, -c) for d, t, c in rows]


# ----- determinism -----


def test_same_seed_gives_byte_identical_files(tmp_path: Path, out_dir: Path) -> None:
    again = tmp_path / "again"
    generate.main(["--out", str(again), "--seed", str(SEED), "--start-month", START_MONTH])

    first = {p.name: p.read_bytes() for p in out_dir.iterdir()}
    second = {p.name: p.read_bytes() for p in again.iterdir()}

    assert first.keys() == second.keys()
    assert first == second


def test_different_seed_gives_different_files(tmp_path: Path, out_dir: Path) -> None:
    other = tmp_path / "other"
    generate.main(["--out", str(other), "--seed", str(SEED + 1), "--start-month", START_MONTH])

    assert (other / "persona_a.csv").read_bytes() != (out_dir / "persona_a.csv").read_bytes()
    assert (other / "golden_set.csv").read_bytes() != (out_dir / "golden_set.csv").read_bytes()


def test_manifest_hashes_match_the_files(out_dir: Path) -> None:
    manifest = json.loads((out_dir / "MANIFEST.json").read_text(encoding="utf-8"))

    from hashlib import sha256

    for name, digest in manifest["sha256"].items():
        assert sha256((out_dir / name).read_bytes()).hexdigest() == digest


def test_committed_samples_are_in_sync_with_the_generator(tmp_path: Path) -> None:
    manifest = json.loads((SAMPLES_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    files, _ = generate.build_files(manifest["seed"], generate.parse_month(manifest["start_month"]))

    for name, content in files.items():
        if name.endswith(".pdf"):  # PDF bytes depend on the installed reportlab version
            assert (SAMPLES_DIR / name).exists()
            continue
        assert (SAMPLES_DIR / name).read_bytes() == content, name


# ----- twins -----


@pytest.mark.parametrize("name", ["persona_a", "persona_b", "persona_c"])
def test_checking_formats_represent_exactly_the_same_transactions(
    name: str, out_dir: Path, statements: dict[str, object]
) -> None:
    stmt = statements[name]
    expected = Counter(_expected(stmt))

    ofx_v1 = parse_ofx((out_dir / f"{name}.ofx").read_bytes(), "latin-1")
    ofx_v2 = parse_ofx((out_dir / f"{name}_v2.ofx").read_bytes(), "utf-8")
    csv_rows = parse_csv((out_dir / f"{name}.csv").read_bytes())
    pdf_rows = parse_pdf((out_dir / f"{name}.pdf").read_bytes())

    for rows in (ofx_v1, ofx_v2, csv_rows, pdf_rows):
        assert Counter(rows) == expected
        assert sum(c for _, _, c in rows) == sum(c for _, _, c in _expected(stmt))


def test_card_formats_are_twins_with_inverted_sign(
    out_dir: Path, statements: dict[str, object]
) -> None:
    stmt = statements["persona_b_card"]
    expected = Counter(_expected(stmt))

    csv_rows = _as_text_sign(stmt, parse_csv((out_dir / "persona_b_card.csv").read_bytes()))
    pdf_rows = _as_text_sign(stmt, parse_pdf((out_dir / "persona_b_card.pdf").read_bytes()))

    assert Counter(csv_rows) == expected
    assert Counter(pdf_rows) == expected


def test_unknown_header_csv_has_the_same_rows_as_persona_a(
    out_dir: Path, statements: dict[str, object]
) -> None:
    rows = parse_csv((out_dir / "persona_a_unknown_header.csv").read_bytes())

    assert Counter(rows) == Counter(_expected(statements["persona_a"]))


def test_manifest_counts_and_sums_match_the_statements(
    out_dir: Path, statements: dict[str, object]
) -> None:
    manifest = json.loads((out_dir / "MANIFEST.json").read_text(encoding="utf-8"))

    for name, stmt in statements.items():
        assert manifest["statements"][name]["rows"] == len(stmt.txns)  # type: ignore[attr-defined]
        assert manifest["statements"][name]["sum_cents"] == sum(
            t.amount_cents
            for t in stmt.txns  # type: ignore[attr-defined]
        )


def test_every_statement_has_between_40_and_60_rows(statements: dict[str, object]) -> None:
    for name, stmt in statements.items():
        assert 40 <= len(stmt.txns) <= 60, name  # type: ignore[attr-defined]


def test_fitids_are_unique_and_signs_match_the_ofx_type(out_dir: Path) -> None:
    for name in ("persona_a", "persona_b", "persona_c"):
        text = (out_dir / f"{name}.ofx").read_bytes().decode("latin-1")
        blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, re.S)
        fitids = [_ofx_field(b, "FITID") for b in blocks]
        assert len(set(fitids)) == len(fitids)
        for block in blocks:
            negative = _ofx_field(block, "TRNAMT").startswith("-")
            assert (_ofx_field(block, "TRNTYPE") == "DEBIT") == negative


# ----- mandatory cases -----


def test_persona_a_has_two_identical_purchases_on_the_same_day(
    statements: dict[str, object], out_dir: Path
) -> None:
    rows = Counter(_expected(statements["persona_a"]))
    twins = [row for row, count in rows.items() if count >= 2]

    assert twins
    fitids = [
        _ofx_field(b, "FITID")
        for b in re.findall(
            r"<STMTTRN>(.*?)</STMTTRN>", (out_dir / "persona_a.ofx").read_text("latin-1"), re.S
        )
    ]
    assert len(set(fitids)) == len(fitids)  # distinct FITIDs even for identical rows


def test_card_statement_lists_purchases_as_positive_numbers(out_dir: Path) -> None:
    rows = parse_csv((out_dir / "persona_b_card.csv").read_bytes())
    purchases = [c for _, text, c in rows if text != "PAGAMENTO RECEBIDO"]

    assert purchases
    assert all(c > 0 for c in purchases)


def test_bill_payment_pairs_checking_debit_with_card_credit(statements: dict[str, object]) -> None:
    checking = statements["persona_b"].txns  # type: ignore[attr-defined]
    card = statements["persona_b_card"].txns  # type: ignore[attr-defined]

    payment = next(t for t in checking if t.description == "PAGAMENTO FATURA CARTAO")
    received = next(t for t in card if t.description == "PAGAMENTO RECEBIDO")
    first_month = [t for t in card if t is not received and t.date.month == card[0].date.month]

    assert payment.amount_cents < 0
    assert received.amount_cents == -payment.amount_cents
    assert received.date == payment.date
    assert -sum(t.amount_cents for t in first_month) == received.amount_cents


def test_csv_variants_cover_separator_number_date_and_column_cases(out_dir: Path) -> None:
    signed = (out_dir / "persona_a.csv").read_text("utf-8").splitlines()
    debit_credit = (out_dir / "persona_b.csv").read_text("utf-8").splitlines()
    currency = (out_dir / "persona_c.csv").read_text("utf-8")
    unknown = (out_dir / "persona_a_unknown_header.csv").read_text("utf-8").splitlines()

    assert signed[0] == "data;descricao;valor"
    assert re.search(r";\d{1,3}\.\d{3},\d{2}\b", "\n".join(debit_credit))
    assert re.match(r"\d{2}/\d{2}/\d{4};", signed[1])
    assert debit_credit[0].split(";")[2:] == ["Débito", "Crédito"]
    assert "R$ " in currency
    assert not {"data", "descricao", "historico", "lancamento", "valor"} & {
        h.lower() for h in unknown[0].split(";")
    }


def test_ofx_v1_is_sgml_latin_1_and_v2_is_xml(out_dir: Path) -> None:
    v1 = (out_dir / "persona_a.ofx").read_bytes()
    v2 = (out_dir / "persona_a_v2.ofx").read_bytes()

    assert v1.startswith(b"OFXHEADER:100")
    assert b"CHARSET:8859-1" in v1
    assert "IMPRESSÕES".encode("latin-1") in v1
    assert b"</TRNAMT>" not in v1
    assert v2.startswith(b"<?xml")
    assert b"</TRNAMT>" in v2


def test_each_persona_repeats_one_fixed_amount_in_both_months(
    statements: dict[str, object],
) -> None:
    for name in ("persona_a", "persona_b", "persona_b_card", "persona_c"):
        by_row: dict[tuple[str, int], set[int]] = {}
        for t in statements[name].txns:  # type: ignore[attr-defined]
            by_row.setdefault((t.description, t.amount_cents), set()).add(t.date.month)
        assert any(len(months) == 2 for months in by_row.values()), name


def test_each_persona_has_ambiguous_lines(statements: dict[str, object]) -> None:
    ambiguous = re.compile(r"^(PAGAMENTO|COMPRA \d{4} \w+|PIX ENVIADO \w+)$")
    groups = {"a": ["persona_a"], "b": ["persona_b", "persona_b_card"], "c": ["persona_c"]}

    for persona, names in groups.items():
        found = [
            t
            for n in names
            for t in statements[n].txns
            if ambiguous.match(t.description)  # type: ignore[attr-defined]
        ]
        assert found, persona


# ----- golden set -----


@pytest.fixture(scope="module")
def golden() -> tuple[object, ...]:
    return generate.build_golden_set(SEED)


def test_golden_set_has_150_rows_split_50_dev_100_test(golden: tuple[object, ...]) -> None:
    splits = Counter(r.split for r in golden)  # type: ignore[attr-defined]

    assert len(golden) == 150
    assert splits == {"dev": 50, "test": 100}


def test_golden_set_mix_is_about_60_25_15_in_each_split(golden: tuple[object, ...]) -> None:
    for split, size in (("dev", 50), ("test", 100)):
        mix = Counter(r.stratum for r in golden if r.split == split)  # type: ignore[attr-defined]
        assert abs(mix["common"] / size - 0.60) <= 0.05
        assert abs(mix["ambiguous"] / size - 0.25) <= 0.05
        assert abs(mix["hard"] / size - 0.15) <= 0.05


def test_golden_labels_are_valid_for_their_sign(golden: tuple[object, ...]) -> None:
    for row in golden:
        assert row.true_category in CATEGORIES  # type: ignore[attr-defined]
        assert is_allowed(row.true_category, row.amount_cents)  # type: ignore[attr-defined]


def test_golden_csv_has_the_documented_columns(out_dir: Path) -> None:
    with (out_dir / "golden_set.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert list(rows[0]) == ["description_raw", "amount_cents", "true_category", "split"]
    assert len(rows) == 150
    assert all(int(r["amount_cents"]) != 0 for r in rows)


def test_labeling_sheet_hides_the_labels_and_keeps_the_rows(out_dir: Path) -> None:
    with (out_dir / "golden_set_labeling_sheet.csv").open(encoding="utf-8", newline="") as handle:
        sheet = list(csv.DictReader(handle))
    with (out_dir / "golden_set.csv").open(encoding="utf-8", newline="") as handle:
        golden_rows = list(csv.DictReader(handle))

    assert "true_category" not in sheet[0]
    assert "split" not in sheet[0]
    assert {r["category"] for r in sheet} == {""}
    assert [r["description_raw"] for r in sheet] == [r["description_raw"] for r in golden_rows]


def test_catalog_does_not_depend_on_the_classification_rules() -> None:
    forbidden = re.compile(r"^\s*(from|import)\s+app\b", re.M)

    for name in ("generate", "synth_catalog", "synth_personas", "synth_writers", "kappa"):
        source = (SYNTH_DIR / f"{name}.py").read_text(encoding="utf-8")
        assert not forbidden.search(source), name


# ----- no personal data -----

PII_PATTERNS = {
    "cpf": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "cnpj": re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"(?<!\d)\(?\d{2}\)?\s?9?\d{4}-?\d{4}(?!\d)"),
    "long_digits": re.compile(r"\d{6,}"),
}


def test_no_description_looks_like_personal_data(
    statements: dict[str, object], golden: tuple[object, ...]
) -> None:
    descriptions = [t.description for s in statements.values() for t in s.txns]  # type: ignore[attr-defined]
    descriptions += [r.description_raw for r in golden]  # type: ignore[attr-defined]

    for text in descriptions:
        for label, pattern in PII_PATTERNS.items():
            assert not pattern.search(text), (label, text)


def test_no_generated_file_contains_an_email_address(out_dir: Path) -> None:
    for path in out_dir.iterdir():
        if path.suffix != ".pdf":
            assert "@" not in path.read_bytes().decode("latin-1"), path.name


# ----- kappa -----


def test_kappa_is_one_for_identical_labels() -> None:
    assert kappa.cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0


def test_kappa_matches_a_hand_computed_case() -> None:
    # po = 3/4, pe = 0.5*0.25 + 0.5*0.75 = 0.5 -> kappa = 0.5
    assert kappa.cohen_kappa(["x", "x", "y", "y"], ["x", "y", "y", "y"]) == pytest.approx(0.5)


def test_kappa_script_lists_disagreements(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    header = "row_id,description_raw,amount_cents,category\n"
    sheet_a = tmp_path / "a.csv"
    sheet_b = tmp_path / "b.csv"
    sheet_a.write_text(header + "1,NETFLIX,-3990,Assinaturas\n2,PAGAMENTO,-500,Outros\n", "utf-8")
    sheet_b.write_text(header + "1,NETFLIX,-3990,Assinaturas\n2,PAGAMENTO,-500,Compras\n", "utf-8")

    assert kappa.main([str(sheet_a), str(sheet_b)]) == 0

    output = capsys.readouterr().out
    assert "disagreements:      1" in output
    assert "row 2" in output


def test_kappa_rejects_unlabelled_or_mismatched_sheets(tmp_path: Path) -> None:
    header = "row_id,description_raw,amount_cents,category\n"
    full = tmp_path / "full.csv"
    blank = tmp_path / "blank.csv"
    other = tmp_path / "other.csv"
    full.write_text(header + "1,NETFLIX,-3990,Assinaturas\n", "utf-8")
    blank.write_text(header + "1,NETFLIX,-3990,\n", "utf-8")
    other.write_text(header + "2,NETFLIX,-3990,Assinaturas\n", "utf-8")
    read: Callable[[Path], dict[str, dict[str, str]]] = lambda p: kappa.read_sheet(p, "category")  # noqa: E731

    with pytest.raises(ValueError, match="labelled"):
        kappa.compare(read(full), read(blank), "category")
    with pytest.raises(ValueError, match="row_ids"):
        kappa.compare(read(full), read(other), "category")


# ----- TODO tracked in docs/report-notes.md -----


def _real_csv_rows(path: Path, invert_sign: bool = False) -> list[Row]:
    parsed = csv_parser.parse_csv(path.read_bytes(), None, invert_sign, MAX_IMPORT_ROWS)
    return [(r.date, r.description_raw, r.amount_cents) for r in parsed]


@pytest.mark.parametrize("name", ["persona_a", "persona_b", "persona_c"])
def test_real_csv_parser_reads_the_checking_csvs_exactly(
    name: str, out_dir: Path, statements: dict[str, object]
) -> None:
    rows = _real_csv_rows(out_dir / f"{name}.csv")

    assert Counter(rows) == Counter(_expected(statements[name]))


def test_real_csv_parser_reads_the_card_csv_with_invert_sign(
    out_dir: Path, statements: dict[str, object]
) -> None:
    rows = _real_csv_rows(out_dir / "persona_b_card.csv", invert_sign=True)

    assert Counter(rows) == Counter(_expected(statements["persona_b_card"]))


def test_real_csv_parser_asks_for_a_mapping_on_the_unknown_header_file(
    out_dir: Path, statements: dict[str, object]
) -> None:
    path = out_dir / "persona_a_unknown_header.csv"
    with pytest.raises(AppError) as caught:
        _real_csv_rows(path)
    mapping = csv_parser.CsvMapping(date="Dt. Lanç.", description="Detalhe", amount="Montante")

    mapped = csv_parser.parse_csv(path.read_bytes(), mapping, False, MAX_IMPORT_ROWS)

    assert caught.value.code == "mapping_required"
    assert caught.value.details == {"columns": ["Dt. Lanç.", "Detalhe", "Montante"]}
    expected = Counter(_expected(statements["persona_a"]))
    assert Counter((r.date, r.description_raw, r.amount_cents) for r in mapped) == expected


def test_real_csv_parser_reproduces_the_committed_manifest_counts() -> None:
    manifest = json.loads((SAMPLES_DIR / "MANIFEST.json").read_text(encoding="utf-8"))["statements"]

    for name in ("persona_a", "persona_b", "persona_c"):
        rows = _real_csv_rows(SAMPLES_DIR / f"{name}.csv")
        assert (len(rows), sum(c for _, _, c in rows)) == (
            manifest[name]["rows"],
            manifest[name]["sum_cents"],
        )


def _real_ofx(path: Path) -> ofx_parser.OfxResult:
    return ofx_parser.parse_ofx(path.read_bytes(), MAX_IMPORT_ROWS)


@pytest.mark.parametrize("suffix", [".ofx", "_v2.ofx"], ids=["sgml-v1-latin1", "xml-v2-utf8"])
@pytest.mark.parametrize("name", ["persona_a", "persona_b", "persona_c"])
def test_real_ofx_parser_twins_the_csv_exactly(
    name: str, suffix: str, out_dir: Path, statements: dict[str, object]
) -> None:
    result = _real_ofx(out_dir / f"{name}{suffix}")
    csv_rows = _real_csv_rows(out_dir / f"{name}.csv")

    ofx_rows = [(r.date, r.description_raw, r.amount_cents) for r in result.rows]
    assert Counter(ofx_rows) == Counter(csv_rows) == Counter(_expected(statements[name]))
    assert len(ofx_rows) == len(csv_rows)
    assert sum(c for _, _, c in ofx_rows) == sum(c for _, _, c in csv_rows)


@pytest.mark.parametrize("name", ["persona_a", "persona_b", "persona_c"])
def test_real_ofx_parser_gives_every_row_a_unique_fitid_and_a_hint(
    name: str, out_dir: Path
) -> None:
    result = _real_ofx(out_dir / f"{name}.ofx")

    fitids = [r.external_id for r in result.rows]
    assert None not in fitids
    assert len(set(fitids)) == len(fitids)
    assert result.account_hint == "1234"


@pytest.mark.parametrize("name", ["persona_a", "persona_b", "persona_c"])
def test_reimporting_an_ofx_reproduces_the_same_external_ids_in_both_syntaxes(
    name: str, out_dir: Path
) -> None:
    first = _real_ofx(out_dir / f"{name}.ofx")
    again = _real_ofx(out_dir / f"{name}.ofx")
    xml = _real_ofx(out_dir / f"{name}_v2.ofx")

    assert first.rows == again.rows
    assert [r.external_id for r in first.rows] == [r.external_id for r in xml.rows]


def test_committed_ofx_samples_match_the_manifest() -> None:
    manifest = json.loads((SAMPLES_DIR / "MANIFEST.json").read_text(encoding="utf-8"))["statements"]

    for name in ("persona_a", "persona_b", "persona_c"):
        rows = _real_ofx(SAMPLES_DIR / f"{name}.ofx").rows
        assert (len(rows), sum(r.amount_cents for r in rows)) == (
            manifest[name]["rows"],
            manifest[name]["sum_cents"],
        )


@pytest.mark.skip(reason="TODO(B3): parse_pdf does not exist yet; see docs/report-notes.md")
def test_real_pdf_parser_reads_every_synthetic_pdf() -> None: ...
