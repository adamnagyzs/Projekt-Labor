from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from leltariv_contracts.assets import AssetListItem

# Ugyanez a három érték szerepel a leltariv_domain.scanning-ben is (a domainnek nincs
# függősége, ezért nem importálhatja); a tests/test_scanning.py ellenőrzi, hogy egyeznek.
# A scan tábla CHECK-je ezeken felül a SURPLUS-t is engedi: az a 7. mérföldkő.
ScanResult = Literal["FOUND", "UNKNOWN_CODE", "FOREIGN_ZONE"]


class SessionCreate(BaseModel):
    zone_code: str


class SessionOut(BaseModel):
    id: UUID
    zone_code: str
    period_name: str
    started_at: datetime


class ScanCreate(BaseModel):
    raw_code: str = Field(min_length=1, max_length=200)


class ScanOut(BaseModel):
    """Egy beolvasás eredménye. A `message` a leltározónak szól, a szerver állítja elő."""

    id: UUID
    raw_code: str
    result: ScanResult
    scanned_at: datetime
    asset: AssetListItem | None = None
    message: str
