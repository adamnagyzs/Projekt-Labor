from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    summary="A szerver működési állapotának ellenőrzése",
)
def health() -> dict[str, str]:
    """Egyszerű, autentikáció nélküli állapotellenőrző végpont."""
    return {"status": "ok"}
