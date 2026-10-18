from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

CodeType = Literal["LELTARSZAM", "ESZKOZSZAM", "GYARI_SZAM", "SAJAT_CIMKE"]


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


class AssetTypeOut(BaseModel):
    id: int
    name: str


class AssetTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AssetTypeSet(BaseModel):
    asset_type_id: int


class ResponsibleSet(BaseModel):
    person_id: UUID
