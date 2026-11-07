from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

CodeType = Literal["LELTARSZAM", "ESZKOZSZAM", "GYARI_SZAM", "SAJAT_CIMKE"]

#: Az eszköz állapota. Törlés nincs: a selejtezett vagy elveszett eszköz sora megmarad, csak
#: az állapota változik. Ugyanezek az értékek a `leltariv_domain.comparison`-ben (teszt
#: ellenőrzi) és az adatbázis `ck_asset_status` megkötésében.
AssetStatus = Literal["ACTIVE", "SCRAPPED", "LOST", "STOLEN", "OTHER"]

#: a felületen megjelenő nevek; a kliens innen veszi, ne írja át saját szövegre
STATUS_LABELS: dict[AssetStatus, str] = {
    "ACTIVE": "Aktív",
    "SCRAPPED": "Selejtezett",
    "LOST": "Elveszett",
    "STOLEN": "Ellopott",
    "OTHER": "Egyéb (nem használt)",
}


class AssetCodeOut(BaseModel):
    code: str
    code_type: CodeType
    is_primary: bool


class PersonOut(BaseModel):
    id: UUID
    name: str
    org_unit: str | None = None


class AssetListItem(BaseModel):
    id: UUID
    asset_number: str
    sub_number: int
    name: str
    zone_code: str
    inventory_number: str | None = None
    quantity: int = 1
    activated_on: date | None = None
    serial_number: str | None = None
    asset_type: str | None = None
    #: a jelenlegi felelős neve
    responsible: str | None = None
    status: AssetStatus = "ACTIVE"


class AssetPage(BaseModel):
    items: list[AssetListItem]
    total: int
    page: int
    page_size: int


class AssetDetail(BaseModel):
    """Egy eszköz adatlapja: a kódjai és, ha főeszköz, a tartozékai."""

    id: UUID
    asset_number: str
    sub_number: int
    name: str
    zone_code: str
    quantity: int
    activated_on: date | None = None
    serial_number: str | None = None
    asset_type: str | None = None
    asset_type_id: int | None = None
    #: ahol az aktív időszakban utoljára beolvasták (vissza nem vont beolvasással)
    room: str | None = None
    responsible: PersonOut | None = None
    codes: list[AssetCodeOut]
    accessories: list[AssetListItem]
    status: AssetStatus = "ACTIVE"


class AssetTypeOut(BaseModel):
    id: int
    name: str


class AssetTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AssetTypeSet(BaseModel):
    asset_type_id: int


class ResponsibleSet(BaseModel):
    person_id: UUID


class StatusChangeCreate(BaseModel):
    """Állapotváltás kérése. Az indoklás kötelező: a történetben ez magyarázza a váltást."""

    status: AssetStatus
    reason: str = Field(min_length=1, max_length=500)


class StatusChangeOut(BaseModel):
    id: UUID
    asset_id: UUID
    old_status: AssetStatus
    new_status: AssetStatus
    reason: str
    changed_at: datetime
    #: a váltást rögzítő felhasználó megjelenített neve
    changed_by: str | None = None


#: CREATED: felvétel importtal; STATUS: állapotváltás; RESPONSIBLE: felelős lett;
#: SCAN: beolvasás; UNDO: beolvasás visszavonása
HistoryKind = Literal["CREATED", "STATUS", "RESPONSIBLE", "SCAN", "UNDO"]


class HistoryEntry(BaseModel):
    """Az eszköz történetének egy sora. A `text` a felhasználónak szól, a szerver állítja elő."""

    at: datetime
    kind: HistoryKind
    text: str
    by: str | None = None
    #: beolvasásnál a leltári időszak neve
    period: str | None = None
