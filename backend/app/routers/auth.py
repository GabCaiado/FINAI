from datetime import datetime, timedelta
from typing import Literal, TypedDict

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.deps import CurrentUser, DbSession, Now
from app.models import User
from app.rate_limit import limiter, login_limit
from app.schemas.auth import LoginIn, RegisterIn, UserOut
from app.security import SESSION_COOKIE_NAME, create_token
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


class _CookieAttributes(TypedDict):
    httponly: bool
    samesite: Literal["lax"]
    path: str


# Every fixed cookie attribute lives here once, so setting and clearing cannot drift apart.
_COOKIE_ATTRIBUTES = _CookieAttributes(httponly=True, samesite="lax", path="/")


def _start_session(response: Response, user: User, now: datetime) -> None:
    lifetime = timedelta(hours=settings.jwt_expire_hours)
    token = create_token(user.id, secret=settings.jwt_secret, now=now, expires_in=lifetime)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=int(lifetime.total_seconds()),
        secure=settings.cookie_secure,
        **_COOKIE_ATTRIBUTES,
    )


def _end_session(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        secure=settings.cookie_secure,
        **_COOKIE_ATTRIBUTES,
    )


@router.post("/auth/register", status_code=201)
def register(data: RegisterIn, response: Response, db: DbSession, now: Now) -> UserOut:
    user = auth_service.register_user(db, data, now)
    _start_session(response, user, now)
    return UserOut.model_validate(user)


@router.post("/auth/login")
@limiter.limit(login_limit)
def login(request: Request, data: LoginIn, response: Response, db: DbSession, now: Now) -> UserOut:
    user = auth_service.authenticate(db, data.email, data.password)
    _start_session(response, user, now)
    return UserOut.model_validate(user)


@router.post("/auth/logout", status_code=204)
def logout() -> Response:
    """Stateless: the JWT itself cannot be revoked (decision D-11), so this only clears the
    cookie. It needs no session, so a user with an expired one can still clear it."""
    response = Response(status_code=204)
    _end_session(response)
    return response


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.delete("/me", status_code=204)
def delete_me(user: CurrentUser, db: DbSession) -> Response:
    auth_service.delete_user(db, user)
    response = Response(status_code=204)
    _end_session(response)
    return response
