# Synthetic data and golden set (P1.3)

Everything here is **invented**: person names, merchants' amounts, accounts. No real statement may
ever be added to the repository, to tests or to fixtures.

## Reproduce

```bash
python data/synthetic/generate.py --out data/synthetic/out --seed 42
python data/synthetic/kappa.py labeler_a.csv labeler_b.csv
```

- `--out` and `--seed` are required; `--start-month YYYY-MM` is optional (default `2026-09`, fixed so
  that a seed alone reproduces the files).
- Same seed + same start month => byte-identical files (proved by `backend/tests/test_synthetic.py`).
  PDF bytes also depend on the installed `reportlab` version (`reportlab` is a dev-only dependency).
- `samples/` is the committed output of `--seed 42`. Runs written to `out/` (or anywhere else) are not
  versioned (`data/synthetic/out/` is git-ignored). `samples/` is marked `-text` in `.gitattributes`
  because the OFX v1 files use CRLF.
- Code: `generate.py` (CLI, golden set, manifest), `synth_personas.py` (transactions),
  `synth_writers.py` (OFX/CSV/PDF), `synth_catalog.py` (merchant catalogs), `kappa.py`.

## Files per run

Three personas, two calendar months each. Each file has 40 to 60 rows. All formats of one statement
are rendered from the same in-memory list, so **count and sum are identical** ("twins").

| File | What it is | Why it exists |
| --- | --- | --- |
| `persona_a.*` | Student on a small allowance (iFood, Uber, mercado, xerox, PIX to colleagues) | Fixed income `PIX RECEBIDO ...` and fixed `SPOTIFY BRASIL` repeat in both months (recurrence); ambiguous `PIX ENVIADO JOAO`, `PAGAMENTO`, `COMPRA 1234 LOJA`; **two identical purchases on 12 of the first month** (`IFOOD *PASTELARIA DO ZE`, same date, amount, description) that must both survive dedupe |
| `persona_b.*` | First job, checking account | Salary, gym, mobile plan, rent via PIX repeat monthly; `PAGAMENTO FATURA CARTAO` on the 10th of month 2 |
| `persona_b_card.csv/.pdf` | Credit-card statement of persona B | **Purchases are POSITIVE numbers** (inverted convention, needs `invert_sign`); fixed Netflix/Spotify/Prime; a `PAGAMENTO RECEBIDO` credit on the 10th of month 2 |
| `persona_c.*` | Freelancer, irregular income | 4 PIX receipts a month with very different values, taxes (`DAS SIMPLES NACIONAL`), tools, coworking |
| `golden_set.csv` | 150 rows for evaluation | See below |
| `golden_set_labeling_sheet.csv` | Same rows without `true_category` | For two people to label independently |
| `MANIFEST.json` | seed, start month, rows and sum per statement, SHA-256 of every file | Determinism check and quick twin sanity |

Formats of each checking persona (`persona_X`):

| File | Format |
| --- | --- |
| `persona_X.ofx` | OFX v1 (SGML, CRLF, no closing leaf tags), `CHARSET:8859-1`, bytes encoded Latin-1 (persona A has `IMPRESSÕES`) |
| `persona_X_v2.ofx` | OFX v2 (XML, UTF-8) |
| `persona_X.csv` | `;` separator, `DD/MM/YYYY`, `1.234,56`. A: `data;descricao;valor`. B: separate `Débito`/`Crédito` columns. C: `-R$ 1.234,56` currency prefix |
| `persona_X.pdf` | The single supported layout `DD/MM/YYYY  DESCRIPTION  -1.234,56`, 42 rows per page |
| `persona_a_unknown_header.csv` | Same rows as A with headers `Dt. Lanç.;Detalhe;Montante`, to exercise the 422 `mapping_required` flow |

Notes for the parsers:

- OFX: `TRNAMT` is signed (negative = out), `FITID` is unique per file, the description is in `MEMO`
  (no `NAME`). Card statements are **not** provided as OFX: OFX signs are standard, the inversion
  only exists in the CSV/PDF text.
- `pdfplumber` collapses the two spaces of the PDF layout into one when extracting text: the PDF
  line regex must use `\s+`.
- Standard convention in the model: income > 0, expense < 0. Card CSV/PDF show the opposite.
- **Bill-payment pair:** checking `PAGAMENTO FATURA CARTAO` (-X) and card `PAGAMENTO RECEBIDO`
  (credit X, shown as `-X` in the card CSV/PDF) have the same date; X equals the month-1 card
  purchases. The generator derives X from the card rows, so they cannot drift apart.

## Golden set

`golden_set.csv`: `description_raw,amount_cents,true_category,split`, 150 rows, `split` = `dev` (50) or
`test` (100). Each split has the same mix: 60% common merchants, 25% ambiguous (PIX to a person,
`PAGAMENTO`, `COMPRA 1234 LOJA`), 15% hard (truncated, gateway-prefixed or opaque strings).

- The rows are drawn from `synth_catalog.py`, written from public knowledge of merchants. It does
  **not** import or copy `app/ai/rules.py`, so the golden set is not biased towards the rules. The
  label comes from the catalog; a test checks it is in `app.categories.CATEGORIES` and allowed for
  the sign.
- Convention behind some labels (the human labelers should confirm or overrule it): PIX/TED to or
  from a person -> `Transferências`; bare `PAGAMENTO`, boleto, saque, débito automático -> `Outros`;
  `COMPRA NNNN LOJA` -> `Compras`; internet/energy/water/rent -> `Moradia`; mobile plan ->
  `Assinaturas`; gym -> `Saúde`; taxes and fees -> `Taxas e Serviços`.
- **Independent labelling (human step, not done here).** Give `golden_set_labeling_sheet.csv` to two
  people who have not seen `golden_set.csv` or `rules.py`. Each fills the `category` column of their
  own copy, then:

  ```bash
  python data/synthetic/kappa.py labeler_a.csv labeler_b.csv
  ```

  It prints observed agreement, Cohen's kappa and every disagreement to resolve together. Record the
  kappa in `docs/report-notes.md` (and the final labels replace `true_category` if the pair agrees
  the catalog label is wrong).
- Do not open the `test` split while tuning rules or prompts (ARCHITECTURE section 16).

## Tests

`backend/tests/test_synthetic.py`: determinism, twin equality across OFX v1/v2, CSV and PDF,
mandatory cases, the 50/100 split and 60/25/15 mix, no CPF/CNPJ/e-mail/phone/long digit runs,
labels inside `CATEGORIES`, kappa maths, committed samples in sync with the generator. The tests that
feed these files to the **real** parsers are skipped placeholders (B2, B2b, B3 turn them on).
