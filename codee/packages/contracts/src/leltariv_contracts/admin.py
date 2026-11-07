from datetime import datetime

from pydantic import BaseModel, Field


class ImportResult(BaseModel):
    file_name: str
    rows_read: int
    #: újonnan felvett eszközök
    rows_ok: int
    #: már az adatbázisban lévő eszközök, változatlanul hagyva
    rows_skipped: int
    rows_failed: int
    #: az első néhány hibás sor, „12. sor: …” alakban
    errors: list[str]
    #: az import előtti állapot pillanatképe; ebből vonható vissza
    snapshot: str


class SnapshotOut(BaseModel):
    file_name: str
    created_at: datetime
    size_bytes: int


class SnapshotCreate(BaseModel):
    #: rövid megjegyzés, a fájlnévbe kerül
    label: str | None = Field(default=None, max_length=40)


class RestoreResult(BaseModel):
    file_name: str
    #: táblánként a visszatöltött sorok száma
    rows: dict[str, int]
    #: a visszatöltés előtti állapot pillanatképe
    backup: str
