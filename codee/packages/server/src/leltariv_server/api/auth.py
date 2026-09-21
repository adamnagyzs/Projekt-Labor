from fastapi import APIRouter, HTTPException, status
from leltariv_contracts.auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Felhasználó bejelentkeztetése",
)
def login(request: LoginRequest) -> LoginResponse:
    """A későbbi GoTrue vagy local auth belépési pontja."""
    del request

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="A hitelesítés még nincs konfigurálva.",
    )