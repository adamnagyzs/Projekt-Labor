"""Pillanatképek: az adatbázis állapota JSON-fájlban, listázva és visszatölthetően.

A fájlok a szerver gépén, a `SNAPSHOT_DIR` mappában vannak (alapból a workspace
`snapshots` mappájában). A fájlnév elején az időpont áll, így név szerint rendezve
időrendben vannak.
"""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from leltariv_contracts.admin import RestoreResult, SnapshotCreate, SnapshotOut
from leltariv_infrastructure.db.session import engine, get_db_session
from leltariv_infrastructure.db.snapshot import dump, restore
from sqlalchemy.orm import Session

from leltariv_server.dependencies import require_admin

router = APIRouter(prefix="/api/v1", tags=["snapshots"])

FILE_NAME_PATTERN = re.compile(r"[\w.-]+\.json")


def snapshot_dir() -> Path:
    configured = os.environ.get("SNAPSHOT_DIR")
    # api → leltariv_server → src → server → packages → workspace
    path = Path(configured) if configured else Path(__file__).resolve().parents[5] / "snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_out(path: Path) -> SnapshotOut:
    stat = path.stat()
    return SnapshotOut(
        file_name=path.name,
        created_at=datetime.fromtimestamp(stat.st_mtime, UTC),
        size_bytes=stat.st_size,
    )


def save_snapshot(label: str | None) -> Path:
    """A mostani állapotot fájlba írja, és visszaadja az útvonalát.

    Külön kapcsolaton, REPEATABLE READ tranzakcióban olvas, hogy egy közben érkező
    beolvasás ne kerülhessen be félig (a munkamenete nélkül).
    """
    slug = re.sub(r"[^\w-]+", "-", label or "").strip("-")
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = snapshot_dir() / (f"{stamp}_{slug}.json" if slug else f"{stamp}.json")

    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        data = dump(connection)

    try:
        # "x": meglévő fájlt nem írunk felül
        with path.open("x", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, default=str)
    except FileExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ebben a másodpercben már készült ilyen nevű pillanatkép.",
        ) from exc
    return path


@router.get(
    "/snapshots",
    response_model=list[SnapshotOut],
    summary="A mentett pillanatképek, a legfrissebb elöl",
)
def list_snapshots(_admin: object = Depends(require_admin)) -> list[SnapshotOut]:  # noqa: B008
    paths = sorted(snapshot_dir().glob("*.json"), key=lambda p: p.name, reverse=True)
    return [snapshot_out(path) for path in paths]


@router.post(
    "/snapshots",
    response_model=SnapshotOut,
    status_code=status.HTTP_201_CREATED,
    summary="Pillanatkép mentése a mostani állapotról",
)
def create_snapshot(
    payload: SnapshotCreate,
    _admin: object = Depends(require_admin),  # noqa: B008
) -> SnapshotOut:
    return snapshot_out(save_snapshot(payload.label))


@router.post(
    "/snapshots/{file_name}/restore",
    response_model=RestoreResult,
    summary="Az adatbázis visszaállítása egy pillanatképre",
)
def restore_snapshot(
    file_name: str,
    _admin: object = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> RestoreResult:
    # Csak a mappában lévő fájl jöhet szóba: a minta perjelet nem enged, tehát kilépni sem.
    path = snapshot_dir() / file_name
    if not FILE_NAME_PATTERN.fullmatch(file_name) or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nincs ilyen pillanatkép.",
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A pillanatkép sérült, nem olvasható JSON.",
        ) from exc

    backup = save_snapshot("visszatoltes-elott")
    try:
        rows = restore(session, data)
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return RestoreResult(file_name=file_name, rows=rows, backup=backup.name)
