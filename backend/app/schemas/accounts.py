from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

ACCOUNT_NAME_MAX_LENGTH = 60

# Must list exactly ``app.models.ACCOUNT_KINDS`` (a test enforces it): the CHECK constraint
# in the database is the last line of defence, this gives the API a precise 422 first.
AccountKind = Literal["checking", "credit_card", "cash"]
AccountName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=ACCOUNT_NAME_MAX_LENGTH),
]


class AccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: AccountName
    kind: AccountKind


class AccountPatch(BaseModel):
    """Partial update: send only what changes. Sending nothing, or an explicit null, is invalid."""

    model_config = ConfigDict(extra="forbid")

    name: AccountName | None = None
    kind: AccountKind | None = None

    @model_validator(mode="after")
    def _only_real_changes(self) -> "AccountPatch":
        sent = {field: getattr(self, field) for field in self.model_fields_set}
        if not sent or any(value is None for value in sent.values()):
            raise ValueError("send at least one field, and no field as null")
        return self


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: AccountKind
