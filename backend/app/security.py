"""Password hashing and session tokens: pure functions, no database, no framework, no clock.

Time is always an explicit ``now`` argument so expiry is testable without sleeping.
"""

import secrets
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Name of the session cookie. Shared by the dependency that reads it and the router that sets it.
SESSION_COOKIE_NAME = "finai_session"

JWT_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["sub", "iat", "exp"]

# Library defaults on purpose (argon2id with the parameters argon2-cffi recommends).
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True only for a matching password; a mismatch or an unusable stored hash is just False."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Verified against when the e-mail is unknown, so "no such user" costs the same hashing work as
# "wrong password" and response time does not reveal which e-mails exist.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def create_token(subject: str, *, secret: str, now: datetime, expires_in: timedelta) -> str:
    claims = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
    }
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str, *, secret: str, now: datetime) -> str | None:
    """Return the subject of a valid, unexpired token, else ``None``.

    Callers must not distinguish the reasons (expired, forged, wrong algorithm...): they all mean
    "not authenticated". Only HS256 is accepted, which also rejects ``alg=none``.
    """
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            # PyJWT checks exp/iat against the real clock; we check against ``now`` below.
            options={"require": _REQUIRED_CLAIMS, "verify_exp": False, "verify_iat": False},
        )
    except jwt.InvalidTokenError:
        return None
    expires_at, issued_at = claims["exp"], claims["iat"]
    if not isinstance(expires_at, int) or not isinstance(issued_at, int):
        return None
    if expires_at <= int(now.timestamp()):
        return None
    return str(claims["sub"])
