from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.config import settings

# Upper bounds keep a hostile payload from forcing megabytes through the password hasher.
PASSWORD_MAX_LENGTH = 128
EMAIL_MAX_LENGTH = 254  # RFC 5321 limit for a mailbox address
NAME_MAX_LENGTH = 100

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH)
]


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=EMAIL_MAX_LENGTH)
    password: str = Field(min_length=settings.password_min_length, max_length=PASSWORD_MAX_LENGTH)
    name: Name
    consent: bool


class LoginIn(BaseModel):
    """No format or strength checks here: a login attempt never reveals the password policy
    or whether an e-mail looks valid. The service normalises the e-mail."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=EMAIL_MAX_LENGTH)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
