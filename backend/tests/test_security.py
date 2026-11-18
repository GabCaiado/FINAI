from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.security import (
    DUMMY_PASSWORD_HASH,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

SECRET = "unit-test-secret-" + "0123456789abcdef" * 4  # long enough for HS512 too
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


def test_password_round_trip_verifies_the_right_password():
    stored = hash_password("correct-horse")
    assert verify_password(stored, "correct-horse") is True


def test_wrong_password_does_not_verify():
    assert verify_password(hash_password("correct-horse"), "wrong-horse") is False


def test_same_password_hashes_differently_each_time():
    assert hash_password("same") != hash_password("same")


@pytest.mark.parametrize("unusable", ["", "x", "not-an-argon2-hash"])
def test_unusable_stored_hash_is_a_failed_verification_not_an_error(unusable: str):
    assert verify_password(unusable, "anything") is False


def test_dummy_hash_is_a_real_hash_that_matches_nothing_guessable():
    assert DUMMY_PASSWORD_HASH.startswith("$argon2id$")
    assert verify_password(DUMMY_PASSWORD_HASH, "password") is False


def test_token_round_trip_returns_the_subject():
    token = create_token("user-1", secret=SECRET, now=NOW, expires_in=DAY)
    assert decode_token(token, secret=SECRET, now=NOW + timedelta(hours=1)) == "user-1"


def test_token_is_rejected_from_the_expiry_instant_on():
    token = create_token("user-1", secret=SECRET, now=NOW, expires_in=DAY)
    assert decode_token(token, secret=SECRET, now=NOW + DAY - timedelta(seconds=1)) == "user-1"
    assert decode_token(token, secret=SECRET, now=NOW + DAY) is None


def test_token_signed_with_another_secret_is_rejected():
    token = create_token(
        "user-1", secret="another-secret-also-long-enough-0123456", now=NOW, expires_in=DAY
    )
    assert decode_token(token, secret=SECRET, now=NOW) is None


def test_unsigned_token_is_rejected():
    claims = {"sub": "user-1", "iat": 1, "exp": int((NOW + DAY).timestamp())}
    unsigned = jwt.encode(claims, None, algorithm="none")
    assert decode_token(unsigned, secret=SECRET, now=NOW) is None


def test_other_hmac_algorithms_are_rejected():
    claims = {"sub": "user-1", "iat": 1, "exp": int((NOW + DAY).timestamp())}
    token = jwt.encode(claims, SECRET, algorithm="HS512")
    assert decode_token(token, secret=SECRET, now=NOW) is None


@pytest.mark.parametrize("missing", ["sub", "iat", "exp"])
def test_token_missing_a_required_claim_is_rejected(missing: str):
    claims = {"sub": "user-1", "iat": int(NOW.timestamp()), "exp": int((NOW + DAY).timestamp())}
    del claims[missing]
    token = jwt.encode(claims, SECRET, algorithm="HS256")
    assert decode_token(token, secret=SECRET, now=NOW) is None


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c"])
def test_garbage_is_rejected(garbage: str):
    assert decode_token(garbage, secret=SECRET, now=NOW) is None
