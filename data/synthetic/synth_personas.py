"""Builds the in-memory transaction lists. Every file format is rendered from these lists."""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import date

from synth_catalog import CLIENT_NAMES, FICTIONAL_NAMES, decorate

MONTHS_PER_STATEMENT = 2
LAST_SAFE_DAY = 28  # valid in every month, so no spec needs calendar logic
BILL_PAYMENT_DAY = 10
BILL_PAYMENT_DESCRIPTION = "PAGAMENTO FATURA CARTAO"
CARD_PAYMENT_DESCRIPTION = "PAGAMENTO RECEBIDO"


@dataclass(frozen=True, slots=True)
class Txn:
    """Amounts use the standard convention here: negative = money out, positive = money in."""

    date: date
    description: str
    amount_cents: int
    fitid: str


@dataclass(frozen=True, slots=True)
class Statement:
    name: str
    code: str
    kind: str  # "checking" | "card"
    txns: tuple[Txn, ...]
    period_start: date
    period_end: date
    inverted_in_text: bool  # card CSV/PDF list purchases as positive numbers


@dataclass(frozen=True, slots=True)
class Spec:
    """A recurring pattern: `per_month` rows each month, or one fixed row on `fixed_day`."""

    descriptions: tuple[str, ...]
    lo_cents: int
    hi_cents: int
    per_month: int = 1
    sign: int = -1
    fixed_day: int | None = None
    decorated: bool = False


def month_start(first: date, offset: int) -> date:
    index = first.month - 1 + offset
    return date(first.year + index // 12, index % 12 + 1, 1)


def _amount(spec: Spec, rng: random.Random) -> int:
    return spec.sign * rng.randint(spec.lo_cents // 10, spec.hi_cents // 10) * 10


def _expand(
    spec: Spec, months: tuple[date, ...], rng: random.Random
) -> list[tuple[date, str, int]]:
    rows: list[tuple[date, str, int]] = []
    fixed_amount = _amount(spec, rng) if spec.fixed_day else 0
    for first in months:
        for _ in range(spec.per_month):
            day = spec.fixed_day or rng.randint(1, LAST_SAFE_DAY)
            text = rng.choice(spec.descriptions)
            if spec.decorated:
                text = decorate(text, rng)
            rows.append((first.replace(day=day), text, fixed_amount or _amount(spec, rng)))
    return rows


def _finalize(code: str, rows: list[tuple[date, str, int]]) -> tuple[Txn, ...]:
    ordered = sorted(enumerate(rows), key=lambda item: (item[1][0], item[0]))
    return tuple(
        Txn(day, text, cents, f"{code}{day:%Y%m%d}{seq:03d}")
        for seq, (_, (day, text, cents)) in enumerate(ordered, start=1)
    )


def _statement(
    name: str, code: str, kind: str, rows: list[tuple[date, str, int]], months: tuple[date, ...]
) -> Statement:
    last = months[-1]
    end = last.replace(day=calendar.monthrange(last.year, last.month)[1])
    return Statement(name, code, kind, _finalize(code, rows), months[0], end, kind == "card")


def _months(first: date) -> tuple[date, ...]:
    return tuple(month_start(first, i) for i in range(MONTHS_PER_STATEMENT))


def _build(
    specs: tuple[Spec, ...], months: tuple[date, ...], rng: random.Random
) -> list[tuple[date, str, int]]:
    return [row for spec in specs for row in _expand(spec, months, rng)]


def _pix_to(rng: random.Random, count_names: int = 8) -> tuple[str, ...]:
    return tuple(f"PIX ENVIADO {n}" for n in rng.sample(FICTIONAL_NAMES[:14], count_names))


def persona_a(first: date, rng: random.Random) -> Statement:
    """Student on a small allowance."""
    months = _months(first)
    specs = (
        Spec(("PIX RECEBIDO ARMANDO VELLAMAR",), 90000, 90000, fixed_day=5, sign=1),
        Spec(("SPOTIFY BRASIL",), 1190, 1190, fixed_day=8),
        Spec(("IFOOD *RESTAURANTE", "IFOOD *LANCHES"), 1500, 5500, per_month=5, decorated=True),
        Spec(("UBER *TRIP", "99 POP"), 800, 2800, per_month=3),
        Spec(
            ("SUPERMERCADO BOA ESTRELA", "ATACADAO", "MERCADINHO SAO JOSE"),
            2500,
            9000,
            per_month=3,
            decorated=True,
        ),
        Spec(("XEROX E IMPRESSÕES CAMPUS",), 300, 1500, per_month=2),
        Spec(("CANTINA UNIVERSITARIA", "CAFÉ DO CAMPUS"), 600, 2200, per_month=2),
        Spec(_pix_to(rng), 1000, 3500, per_month=3),
        Spec(("PIX ENVIADO JOAO",), 1000, 2500),
        Spec(("PAGAMENTO",), 500, 2000),
        Spec(("COMPRA 1234 LOJA",), 1500, 6000),
    )
    rows = _build(specs, months, rng)
    twin_day, twin_text, twin_cents = months[0].replace(day=12), "IFOOD *PASTELARIA DO ZE", -2490
    rows += [(twin_day, twin_text, twin_cents)] * 2  # dedupe test: identical purchases
    return _statement("persona_a", "A", "checking", rows, months)


def persona_b_checking(first: date, rng: random.Random, bill_cents: int) -> Statement:
    """First job with subscriptions; pays the card bill of month 1 in month 2."""
    months = _months(first)
    specs = (
        Spec(("SALARIO CIA ORLINDOR LTDA",), 380000, 380000, fixed_day=5, sign=1),
        Spec(("SMART FIT ACADEMIA",), 11990, 11990, fixed_day=7),
        Spec(("PLANO CELULAR TIM",), 6990, 6990, fixed_day=15),
        Spec(("PIX ENVIADO SENHORIA ARVELINDA",), 120000, 120000, fixed_day=6),
        Spec(("TARIFA PACOTE SERVICOS",), 2990, 2990, fixed_day=20),
        Spec(
            ("PAO DE ACUCAR", "CARREFOUR HIPERMERCADO", "ASSAI ATACADISTA"),
            4000,
            22000,
            per_month=4,
            decorated=True,
        ),
        Spec(("DROGASIL", "DROGARIA PACHECO"), 1500, 9000, per_month=2),
        Spec(("RESTAURANTE SABOR CASEIRO", "SPOLETO", "GIRAFFAS"), 2500, 6500, per_month=4),
        Spec(("UBER *TRIP", "99 POP"), 900, 3800, per_month=4),
        Spec(_pix_to(rng), 1500, 8000, per_month=2),
        Spec(("PIX RECEBIDO TIAGO ORLINDOR",), 2000, 15000, sign=1),
    )
    rows = _build(specs, months, rng)
    payment_day = months[1].replace(day=BILL_PAYMENT_DAY)
    rows.append((payment_day, BILL_PAYMENT_DESCRIPTION, -bill_cents))
    return _statement("persona_b", "B", "checking", rows, months)


def persona_b_card(first: date, rng: random.Random) -> tuple[Statement, int]:
    """Credit-card statement. Returns it plus the month-1 total that the bill payment must match."""
    months = _months(first)
    specs = (
        Spec(("NETFLIX",), 3990, 3990, fixed_day=9),
        Spec(("SPOTIFY",), 2190, 2190, fixed_day=11),
        Spec(("AMAZON PRIME",), 1490, 1490, fixed_day=13),
        Spec(("IFOOD *RESTAURANTE", "RAPPI BRASIL"), 1800, 6500, per_month=6, decorated=True),
        Spec(("UBER *TRIP",), 900, 3800, per_month=3),
        Spec(("LOJAS RENNER", "SHEIN", "MERCADO LIVRE"), 3000, 25000, per_month=3),
        Spec(("CINEMARK", "STEAM GAMES", "BAR DO ZE"), 2500, 9000, per_month=3),
        Spec(("COMPRA 1234 LOJA", "COMPRA 8841 LOJA"), 1500, 12000, per_month=2),
        Spec(("DROGASIL",), 1500, 6000, per_month=1),
    )
    rows = _build(specs, months, rng)
    first_month_total = -sum(c for d, _, c in rows if d < months[1])
    payment_day = months[1].replace(day=BILL_PAYMENT_DAY)
    rows.append((payment_day, CARD_PAYMENT_DESCRIPTION, first_month_total))
    return _statement("persona_b_card", "BC", "card", rows, months), first_month_total


def persona_c(first: date, rng: random.Random) -> Statement:
    """Freelancer with irregular income."""
    months = _months(first)
    clients = tuple(f"PIX RECEBIDO {c}" for c in CLIENT_NAMES)
    specs = (
        Spec(clients, 50000, 450000, per_month=4, sign=1),
        Spec(("TED RECEBIDA ESTUDIO LUMINARA",), 80000, 300000, sign=1),
        Spec(("DAS SIMPLES NACIONAL",), 7160, 7160, fixed_day=20),
        Spec(("COWORKING ESPACO LIVRE",), 45000, 45000, fixed_day=3),
        Spec(("VIVO FIBRA",), 11990, 11990, fixed_day=14),
        Spec(("ADOBE CREATIVE CLOUD",), 12990, 12990, fixed_day=8),
        Spec(("FIGMA", "GITHUB", "NOTION", "GOOGLE *WORKSPACE"), 1500, 9000, per_month=2),
        Spec(("ENEL DISTRIBUICAO",), 8000, 20000),
        Spec(("CARREFOUR HIPERMERCADO", "EXTRA SUPERMERCADOS"), 4000, 20000, per_month=3),
        Spec(
            ("RESTAURANTE SABOR CASEIRO", "IFOOD *RESTAURANTE", "STARBUCKS"),
            2000,
            7000,
            per_month=3,
        ),
        Spec(("UBER *TRIP", "99 POP"), 900, 4500, per_month=2),
        Spec(_pix_to(rng, 4), 2000, 25000, per_month=2),
        Spec(("PAGAMENTO",), 3000, 40000),
        Spec(("COMPRA 5507 COMERCIO",), 2000, 15000),
    )
    return _statement("persona_c", "C", "checking", _build(specs, months, rng), months)


def build_statements(seed: int, first_month: date) -> tuple[Statement, ...]:
    def rng_for(label: str) -> random.Random:
        return random.Random(f"{seed}:{label}")

    card, bill = persona_b_card(first_month, rng_for("b-card"))
    return (
        persona_a(first_month, rng_for("a")),
        persona_b_checking(first_month, rng_for("b"), bill),
        card,
        persona_c(first_month, rng_for("c")),
    )
