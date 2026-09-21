from typing import cast

from fastapi import APIRouter, Depends
from leltariv_contracts.auth import LoginRequest, LoginResponse, Role
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy.orm import Session

from leltariv_server.services.auth import local_login

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Felhasználó bejelentkeztetése",
)
def login(
    request: LoginRequest,
    session: Session = Depends(get_db_session),  # noqa: B008
) -> LoginResponse:
    """Lokális demólogin vagy később GoTrue-n keresztüli hitelesítés."""
    access_token, refresh_token, user = local_login(
        request.email,
        request.password,
        session,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=cast(Role, user.role),
        display_name=user.display_name or user.role,
    )