from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app import messages
from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.models import User
from app.security import SESSION_COOKIE_NAME, decode_token

DbSession = Annotated[Session, Depends(get_db)]


def get_now() -> datetime:
    """The clock as a dependency, so tests can pin the time with ``dependency_overrides``."""
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(get_now)]


def get_current_user(request: Request, db: DbSession, now: Now) -> User:
    """Resolve the session cookie to a user, loaded from the database on every request.

    Every failure looks the same (missing, forged, expired, deleted user): the caller learns
    nothing about why it was refused.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    subject = decode_token(token, secret=settings.jwt_secret, now=now) if token else None
    user = db.get(User, subject) if subject else None
    if user is None:
        raise AppError("unauthorized", messages.UNAUTHORIZED, 401)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
