from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from leltariv_contracts.assets import AssetListItem

# Ugyanezek az értékek szerepelnek a leltariv_domain.scanning-ben is (a domainnek nincs
# függősége, ezért nem importálhatja); a tests/test_scanning.py ellenőrzi, hogy egyeznek.
ScanResult = Literal["FOUND", "UNKNOWN_CODE", "FOREIGN_ZONE", "SURPLUS"]


class SessionCreate(BaseModel):
    zone_code: str


class SessionOut(BaseModel):
    id: UUID
    zone_code: str
    period_name: str
    started_at: datetime
    closed_at: datetime | None = None


class ScanCreate(BaseModel):
    raw_code: str = Field(min_length=1, max_length=200)
    #: hány darabot számolt meg a leltározó ebből a kódból
    quantity: int = Field(default=1, ge=1, le=9999)
    room_id: UUID | None = None


class ScanOut(BaseModel):
    """Egy beolvasás eredménye. A `message` a leltározónak szól, a szerver állítja elő."""

    id: UUID
    raw_code: str
    result: ScanResult
    scanned_at: datetime
    asset: AssetListItem | None = None
    message: str
    #: előjeles: visszavonásnál negatív
    quantity: int
    room: str | None = None
    #: nyilvántartott és az időszakban eddig beolvasott darab; csak FOUND és SURPLUS esetén
    expected: int | None = None
    counted: int | None = None
    #: visszavonásnál a visszavont beolvasás
    compensates_scan_id: UUID | None = None
