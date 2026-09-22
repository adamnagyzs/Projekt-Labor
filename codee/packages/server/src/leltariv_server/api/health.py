from fastapi import APIRouter, HTTPException, status
from leltariv_infrastructure.db.session import engine
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    summary="A szerver és az adatbázis működési állapota",
)
def health() -> dict[str, str]:
    """Hitelesítés nélküli állapotellenőrzés.

    Az adatbázist is megkérdezi, nem csak azt jelzi, hogy a folyamat él. Enélkül a
    végpont akkor is 200-at adna, ha a Postgres áll, és a hiba csak az első valódi
    kérésnél derülne ki — kérésenként újra, ötszázas hibaként. Így egyetlen hívásból
    megkülönböztethető a három eset: nincs válasz (a szerver áll), 503 (az adatbázis
    nem érhető el), 200 (minden rendben).
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Az adatbázis nem érhető el.",
        ) from error

    return {"status": "ok", "database": "ok"}
