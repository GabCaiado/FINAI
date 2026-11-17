"""Cohen's kappa between two independently labelled copies of golden_set_labeling_sheet.csv.

Usage:  python data/synthetic/kappa.py labeler_a.csv labeler_b.csv [--label-column category]

Prints observed agreement, kappa and the list of disagreements to resolve together.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

ID_COLUMN = "row_id"
DESCRIPTION_COLUMN = "description_raw"
AMOUNT_COLUMN = "amount_cents"


def cohen_kappa(a: list[str], b: list[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("label lists must be non-empty and of equal length")
    total = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / total
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[c] * count_b[c] for c in count_a.keys() | count_b.keys()) / total**2
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def read_sheet(path: Path, label_column: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or label_column not in rows[0]:
        raise ValueError(f"{path}: missing column '{label_column}'")
    return {row[ID_COLUMN]: row for row in rows}


def compare(
    first: dict[str, dict[str, str]], second: dict[str, dict[str, str]], label_column: str
) -> tuple[float, float, list[tuple[str, str, str, str]]]:
    if first.keys() != second.keys():
        raise ValueError("the two sheets do not cover the same row_ids")
    ids = sorted(first, key=int)
    labels_a = [first[i][label_column].strip() for i in ids]
    labels_b = [second[i][label_column].strip() for i in ids]
    if "" in labels_a or "" in labels_b:
        raise ValueError("every row must be labelled in both sheets")
    agreement = sum(x == y for x, y in zip(labels_a, labels_b, strict=True)) / len(ids)
    diffs = [
        (i, first[i][DESCRIPTION_COLUMN], x, y)
        for i, x, y in zip(ids, labels_a, labels_b, strict=True)
        if x != y
    ]
    return agreement, cohen_kappa(labels_a, labels_b), diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cohen's kappa for two labelled sheets.")
    parser.add_argument("sheet_a", type=Path)
    parser.add_argument("sheet_b", type=Path)
    parser.add_argument("--label-column", default="category")
    args = parser.parse_args(argv)
    agreement, kappa, diffs = compare(
        read_sheet(args.sheet_a, args.label_column),
        read_sheet(args.sheet_b, args.label_column),
        args.label_column,
    )
    print(f"observed agreement: {agreement:.3f}")
    print(f"cohen kappa:        {kappa:.3f}")
    print(f"disagreements:      {len(diffs)}")
    for row_id, description, label_a, label_b in diffs:
        print(f"  row {row_id}: {description!r}: A={label_a} | B={label_b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
