"""B2: ``clean`` and ``merchant_key`` (ARCHITECTURE 10.2)."""

import random

import pytest

from app.parsers.cleaning import GENERIC_WORDS, MERCHANT_KEY_TOKENS, clean, merchant_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("COMPRA DEBITO IFOOD *RESTAURANTE", "IFOOD *RESTAURANTE"),
        ("Impressões Xerox", "IMPRESSOES XEROX"),
        ("Pagamento fatura cartão", "PAGAMENTO FATURA"),  # PAGAMENTO is not the word PAG
        ("COMPRA 12/09 NETFLIX 123456", "NETFLIX"),
        ("PIX ENVIADO JOAO 2026-09-12", "PIX ENVIADO JOAO"),
        ("MERCADO 12/09/2026 CENTRO", "MERCADO CENTRO"),
        ("COMPRA 1234 LOJA", "LOJA"),
        ("LOJA1234", "LOJA"),
        ("99 POP", "99 POP"),  # short numbers are part of the name
        ("LOJA 7-11", "LOJA 7-11"),  # not a date
        ("compra pagto pag credito debito cartao", ""),
        ("  UBER   *TRIP  ", "UBER *TRIP"),
        ("", ""),
        ("   ", ""),
        ("12345678", ""),
        ("12/09", ""),
    ],
)
def test_clean_examples(raw: str, expected: str) -> None:
    assert clean(raw) == expected


def test_generic_words_live_in_one_named_constant() -> None:
    assert {"COMPRA", "CARTAO", "DEBITO", "CREDITO", "PAGTO", "PAG"} == GENERIC_WORDS


def test_clean_is_idempotent_on_hand_picked_tricky_inputs() -> None:
    tricky = ["12345/6/7", "1/2/3/4", "12/09/20266", "COMPRA/PAG/1234/5", "1-2-3-4-5", "10/ 09"]

    for text in tricky:
        assert clean(clean(text)) == clean(text), text


def test_clean_is_idempotent_on_random_text() -> None:
    rng = random.Random(20260917)  # seeded: deterministic
    pieces = ["COMPRA", "pag", "Débito", "12/09", "2026-09-12", "1234", "99", "/", "-", "*", " "]
    pieces += ["IFOOD", "café", "12/09/26", "7-11", "5", " ", "ção"]

    for _ in range(2000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 12)))
        once = clean(text)
        assert clean(once) == once, repr(text)


def test_clean_output_is_ascii_uppercase_without_double_spaces() -> None:
    result = clean("  Açaí   da  Praça – 12/09 ")

    assert result.isascii()
    assert result == result.upper()
    assert "  " not in result
    assert result == result.strip()


@pytest.mark.parametrize(
    ("cleaned", "expected"),
    [
        ("IFOOD *RESTAURANTE", "IFOOD RESTAURANTE"),
        ("PIX ENVIADO LETICIA ARVELINDA", "PIX ENVIADO LETICIA"),
        ("SPOTIFY", "SPOTIFY"),
        ("99 POP", "99 POP"),
        ("", ""),
        ("* - /", ""),
    ],
)
def test_merchant_key_is_the_first_meaningful_tokens(cleaned: str, expected: str) -> None:
    assert merchant_key(cleaned) == expected


def test_merchant_key_keeps_at_most_the_configured_number_of_tokens() -> None:
    key = merchant_key("A B C D E F")

    assert len(key.split()) == MERCHANT_KEY_TOKENS == 3
