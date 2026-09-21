from fastapi import APIRouter, HTTPException, Query, status
from leltariv_contracts.assets import AssetPage

router = APIRouter(prefix="/api/v1", tags=["assets"])


@router.get(
    "/assets",
    response_model=AssetPage,
    summary="Eszközök keresése és lapozott lekérdezése",
)
def list_assets(
    zone: str = Query(description="A körzet kódja, például: 261."),
    q: str | None = Query(default=None, description="Szabad szöveges keresőkifejezés."),
    page: int = Query(default=1, ge=1, description="Oldalszám, 1-től kezdve."),
    page_size: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Oldalméret, legfeljebb 100.",
    ),
) -> AssetPage:
    """A seedelt eszközöket fogja szűrni körzet és keresőkifejezés alapján."""
    del zone, q, page, page_size

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Az adatbázis még nincs konfigurálva.",
    )