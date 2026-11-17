"""Deterministic synthetic statements and golden set for FINAI (work package P1.3).

Usage:  python data/synthetic/generate.py --out <dir> --seed <int> [--start-month YYYY-MM]

Same seed and start month give the same files. All data is invented.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from synth_catalog import (  # noqa: E402
    COMMON,
    HARD,
    CatalogEntry,
    ambiguous_entries,
    decorate,
)
from synth_personas import Statement, build_statements  # noqa: E402
from synth_writers import (  # noqa: E402
    render_csv,
    render_csv_debit_credit,
    render_csv_unknown_header,
    render_ofx_v1,
    render_ofx_v2,
    render_pdf,
)

DEFAULT_START_MONTH = "2026-09"  # fixed so that a seed alone reproduces the files
MANIFEST_NAME = "MANIFEST.json"
GOLDEN_NAME = "golden_set.csv"
LABELING_SHEET_NAME = "golden_set_labeling_sheet.csv"
GOLDEN_COLUMNS = ("description_raw", "amount_cents", "true_category", "split")
LABELING_COLUMNS = ("row_id", "description_raw", "amount_cents", "category")

# (stratum, dev rows, test rows): 60% common, 25% ambiguous, 15% hard of 150, split 50/100.
GOLDEN_PLAN = (("common", 30, 60), ("ambiguous", 13, 25), ("hard", 7, 15))


@dataclass(frozen=True, slots=True)
class GoldenRow:
    description_raw: str
    amount_cents: int
    true_category: str
    split: str
    stratum: str


def _draw(entry: CatalogEntry, stratum: str, rng: random.Random) -> tuple[str, int]:
    text = entry.description if stratum == "hard" else decorate(entry.description, rng)
    cents = rng.randint(entry.lo_cents // 10, entry.hi_cents // 10) * 10 or entry.lo_cents
    return text, entry.sign * cents


def build_golden_set(seed: int) -> tuple[GoldenRow, ...]:
    rng = random.Random(f"{seed}:golden")
    pools = {"common": COMMON, "ambiguous": ambiguous_entries(), "hard": HARD}
    rows: list[GoldenRow] = []
    for stratum, dev, test in GOLDEN_PLAN:
        picked = rng.sample(pools[stratum], dev + test)
        for index, entry in enumerate(picked):
            text, cents = _draw(entry, stratum, rng)
            split = "dev" if index < dev else "test"
            rows.append(GoldenRow(text, cents, entry.category, split, stratum))
    rng.shuffle(rows)
    return tuple(rows)


def _csv_bytes(header: tuple[str, ...], rows: list[tuple[object, ...]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def render_golden_csv(rows: tuple[GoldenRow, ...]) -> bytes:
    body: list[tuple[object, ...]] = [
        (r.description_raw, r.amount_cents, r.true_category, r.split) for r in rows
    ]
    return _csv_bytes(GOLDEN_COLUMNS, body)


def render_labeling_sheet(rows: tuple[GoldenRow, ...]) -> bytes:
    """No `true_category` and no split: each labeler fills `category` on their own copy."""
    body: list[tuple[object, ...]] = [
        (i, r.description_raw, r.amount_cents, "") for i, r in enumerate(rows, start=1)
    ]
    return _csv_bytes(LABELING_COLUMNS, body)


def statement_files(stmt: Statement) -> dict[str, bytes]:
    """Every format is rendered from the same in-memory list, so the twins always agree."""
    name = stmt.name
    pdf = render_pdf(stmt)
    if stmt.kind == "card":
        return {f"{name}.csv": render_csv(stmt).encode("utf-8"), f"{name}.pdf": pdf}
    csv_text: Callable[[Statement], str] = {
        "persona_b": render_csv_debit_credit,
        "persona_c": lambda s: render_csv(s, currency=True),
    }.get(name, render_csv)
    files = {
        f"{name}.ofx": render_ofx_v1(stmt),
        f"{name}_v2.ofx": render_ofx_v2(stmt),
        f"{name}.csv": csv_text(stmt).encode("utf-8"),
        f"{name}.pdf": pdf,
    }
    if name == "persona_a":
        files[f"{name}_unknown_header.csv"] = render_csv_unknown_header(stmt).encode("utf-8")
    return files


def parse_month(value: str) -> date:
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def build_files(seed: int, start_month: date) -> tuple[dict[str, bytes], dict[str, dict[str, int]]]:
    files: dict[str, bytes] = {}
    summary: dict[str, dict[str, int]] = {}
    for stmt in build_statements(seed, start_month):
        files.update(statement_files(stmt))
        summary[stmt.name] = {
            "rows": len(stmt.txns),
            "sum_cents": sum(t.amount_cents for t in stmt.txns),
        }
    golden = build_golden_set(seed)
    files[GOLDEN_NAME] = render_golden_csv(golden)
    files[LABELING_SHEET_NAME] = render_labeling_sheet(golden)
    return files, summary


def build_manifest(
    seed: int, start_month: str, files: dict[str, bytes], summary: dict[str, dict[str, int]]
) -> dict[str, object]:
    return {
        "seed": seed,
        "start_month": start_month,
        "statements": summary,
        "sha256": {n: hashlib.sha256(c).hexdigest() for n, c in sorted(files.items())},
    }


def generate(out: Path, seed: int, start_month: str) -> dict[str, object]:
    files, summary = build_files(seed, parse_month(start_month))
    out.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (out / name).write_bytes(content)
    manifest = build_manifest(seed, start_month, files, summary)
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (out / MANIFEST_NAME).write_bytes(text.encode("utf-8"))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate FINAI synthetic data.")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    parser.add_argument("--seed", type=int, required=True, help="random seed")
    parser.add_argument("--start-month", default=DEFAULT_START_MONTH, help="first month, YYYY-MM")
    args = parser.parse_args(argv)
    manifest = generate(args.out, args.seed, args.start_month)
    print(f"wrote {len(manifest['sha256'])} files to {args.out}")  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
