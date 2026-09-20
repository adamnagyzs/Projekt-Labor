from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

CodeType = Literal["LELTARSZAM", "ESZKOZSZAM", "GYARI_SZAM", "SAJAT_CIMKE"]


class AssetCodeOut(BaseModel):
    code: str
    code_type: CodeType
    is_primary: bool


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


class AssetPage(BaseModel):
    items: list[AssetListItem]
    total: int
    page: int
    page_size: int
