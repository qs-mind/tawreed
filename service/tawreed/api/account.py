from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from tawreed.account.session import Account, Unavailable
from tawreed.api.common import problem

router = APIRouter(prefix="/account", tags=["account"])


class PendingSignIn(BaseModel):
    method: Literal["browser", "code"]
    url: str  # where the engineer finishes signing in, should the browser not have opened
    user_code: str | None  # the code to type there (sign-in with a code)


class AccountOut(BaseModel):
    """signed_out: sign in first. active: signed in. offline: the account service can't be reached, Tawreed works
    until lease_ends_at. expired: the lease is over, Tawreed is read-only until it can refresh."""

    state: Literal["signed_out", "active", "offline", "expired"]
    email: str | None
    name: str | None
    plan: str | None  # from the account service when it sends one; the interface says "Free" otherwise
    lease_ends_at: str | None
    pending: PendingSignIn | None
    problem: str | None  # why the last sign-in failed


class SignIn(BaseModel):
    language: Literal["en", "ar"] = "en"


def _account(request: Request) -> Account:
    return request.app.state.account


def _started(start) -> AccountOut:
    try:
        return AccountOut.model_validate(start())
    except Unavailable as error:
        raise problem(503, error.code) from error


@router.get("")
def get_account(request: Request) -> AccountOut:
    return AccountOut.model_validate(_account(request).status())


@router.post("/sign-in")
def sign_in(body: SignIn, request: Request) -> AccountOut:
    """Open the QS Mind account in the system browser. The browser comes back to Tawreed on its own."""
    return _started(lambda: _account(request).sign_in(body.language))


@router.post("/sign-in/code")
def sign_in_with_code(body: SignIn, request: Request) -> AccountOut:
    """Sign in with a short code approved at the account's device page, on this computer or another device."""
    return _started(lambda: _account(request).sign_in_with_code(body.language))


@router.delete("/sign-in", status_code=204)
def cancel_sign_in(request: Request) -> Response:
    _account(request).cancel()
    return Response(status_code=204)


@router.post("/sign-out", status_code=204)
def sign_out(request: Request) -> Response:
    _account(request).sign_out()
    return Response(status_code=204)
