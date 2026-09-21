from fastapi import APIRouter, HTTPException, status
from leltariv_contracts.zones import ZoneOut

router = APIRouter(prefix="/api/v1", tags=["zones"])


@router.get(
    "/zones",
    response_model=list[ZoneOut],
    summary="Leltárkörzetek lekérdezése",
)
def list_zones() -> list[ZoneOut]:
    """A seedelt körzeteket fogja visszaadni Bearer tokennel."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Az adatbázis még nincs konfigurálva.",
    )