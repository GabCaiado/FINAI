from fastapi import APIRouter, Response

from app.deps import CurrentUser, DbSession, Now
from app.schemas.accounts import AccountIn, AccountOut, AccountPatch
from app.services import accounts as accounts_service

router = APIRouter(tags=["accounts"])


@router.get("/accounts")
def list_accounts(user: CurrentUser, db: DbSession) -> list[AccountOut]:
    return [AccountOut.model_validate(a) for a in accounts_service.list_accounts(db, user)]


@router.post("/accounts", status_code=201)
def create_account(data: AccountIn, user: CurrentUser, db: DbSession, now: Now) -> AccountOut:
    return AccountOut.model_validate(accounts_service.create_account(db, user, data, now))


@router.patch("/accounts/{account_id}")
def update_account(
    account_id: str, patch: AccountPatch, user: CurrentUser, db: DbSession
) -> AccountOut:
    account = accounts_service.rename_or_retype_account(db, user, account_id, patch)
    return AccountOut.model_validate(account)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: str, user: CurrentUser, db: DbSession) -> Response:
    accounts_service.delete_account(db, user, account_id)
    return Response(status_code=204)
