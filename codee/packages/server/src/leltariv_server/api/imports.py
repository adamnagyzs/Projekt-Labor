"""SAP-eszközlista (XLSX) feltöltése és betöltése.

A fájl nyers bájtként jön a kérés törzsében (application/octet-stream), a neve a
`file_name` paraméterben: így nem kell külön multipart-függőség.
"""

from io import BytesIO
from typing import Annotated
from zipfile import BadZipFile

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from leltariv_contracts.admin import ImportResult
from leltariv_infrastructure.asset_import import import_file, link_accessories
from leltariv_infrastructure.db.session import get_db_session
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.orm import Session

from leltariv_server.api.snapshots import save_snapshot
from leltariv_server.dependencies import require_admin

router = APIRouter(prefix="/api/v1", tags=["imports"])

#: a két valódi lista 130 és 350 kB; ennél jóval nagyobb fájl nem eszközlista
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: ennyi hibás sort küldünk vissza; a többi a darabszámban látszik
MAX_REPORTED_ERRORS = 20


@router.post(
    "/imports",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="SAP-eszközlista (XLSX) betöltése",
)
def import_xlsx(
    content: Annotated[bytes, Body(media_type="application/octet-stream")],
    file_name: str = Query(min_length=1, max_length=200),
    _admin: object = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> ImportResult:
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="A fájl túl nagy (legfeljebb 20 MB).",
        )

    # Az import előtti állapot mentése: ha a lista rossz volt, ebből visszaállítható.
    snapshot = save_snapshot("import-elott")
    try:
        report = import_file(session, BytesIO(content), file_name)
        link_accessories(session)
        session.commit()
    except (BadZipFile, InvalidFileException, ValueError) as exc:
        session.rollback()
        snapshot.unlink()  # nem változott semmi, nincs mit visszavonni
        detail = str(exc) if isinstance(exc, ValueError) else "A fájl nem XLSX-munkafüzet."
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        ) from exc

    return ImportResult(
        file_name=file_name,
        rows_read=report.rows_read,
        rows_ok=report.rows_ok,
        rows_skipped=report.rows_skipped,
        rows_failed=report.rows_failed,
        errors=[f"{row}. sor: {message}" for row, message in report.errors[:MAX_REPORTED_ERRORS]],
        snapshot=snapshot.name,
    )
