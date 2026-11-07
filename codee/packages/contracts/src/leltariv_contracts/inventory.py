from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from leltariv_contracts.assets import AssetListItem, AssetStatus

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


PeriodState = Literal["DRAFT", "ACTIVE", "CLOSED"]


class PeriodOut(BaseModel):
    """Leltári időszak. Egyszerre legfeljebb egy aktív; a lezárt nem módosítható."""

    id: UUID
    name: str
    year: int | None = None
    state: PeriodState
    opened_at: datetime | None = None
    closed_at: datetime | None = None


class PeriodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=2000, le=2100)


#: FOUND: megvan a nyilvántartott darab (tartozéknál: a főeszköze alapján feltételezzük);
#: PARTIAL: kevesebb került elő; MISSING: egy sem; SURPLUS: több, mint a nyilvántartott
#: (nem aktív eszköznél bármennyi). Ugyanezek a `leltariv_domain.comparison`-ben.
ComparisonCategory = Literal["FOUND", "PARTIAL", "MISSING", "SURPLUS"]

#: DIRECT: van saját beolvasása; INHERITED: nincs, de a főeszközét megtalálták
Verification = Literal["DIRECT", "INHERITED"]


class ComparisonRow(BaseModel):
    """Egy nyilvántartott eszköz a körzetben: mennyi van papíron, mennyi került elő."""

    asset: AssetListItem
    #: az időszak végén érvényes állapot (lezárt időszaknál a lezáráskori)
    status: AssetStatus
    #: nyilvántartott darab; nem aktív eszköznél 0
    expected: int
    counted: int
    #: counted - expected; negatív: hiány, pozitív: többlet
    difference: int
    category: ComparisonCategory
    verification: Verification | None = None
    #: ahol az időszakban utoljára beolvasták
    room: str | None = None
    #: ha itt nem került elő, de egy másik körzetben beolvasták: annak a körzetnek a kódja
    found_in_zone: str | None = None


class ForeignFind(BaseModel):
    """Másik körzetben nyilvántartott eszköz, amely ebben a körzetben került elő."""

    asset: AssetListItem
    home_zone_code: str
    quantity: int
    room: str | None = None


class UnknownCode(BaseModel):
    """Beolvasott kód, amelyhez nem tartozik egyértelműen eszköz."""

    raw_code: str
    quantity: int
    room: str | None = None


class ComparisonSummary(BaseModel):
    #: nyilvántartott, az időszakban aktív eszközök a körzetben
    expected_assets: int
    found: int
    #: a `found`-ból: tartozék, amit csak a főeszköze alapján tekintünk meglévőnek
    inherited: int
    partial: int
    missing: int
    surplus: int
    foreign: int
    unknown: int
    #: a nyilvántartott eszközök hány százaléka került elő legalább részben, 0-100
    progress_percent: float


class ComparisonOut(BaseModel):
    """A forrásadat és a leltár eredményének összevetése egy időszakra és körzetre.

    Minden szám a beolvasási naplóból számolt, tárolt összeg nincs. A sorok sorrendje:
    hiányzó, részleges, többlet, megtalált; azon belül eszközszám szerint.
    """

    period: PeriodOut
    zone_code: str
    summary: ComparisonSummary
    rows: list[ComparisonRow]
    foreign: list[ForeignFind]
    unknown: list[UnknownCode]
