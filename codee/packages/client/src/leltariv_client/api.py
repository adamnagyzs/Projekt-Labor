import time
from uuid import uuid4
from datetime import date
from typing import Protocol

from leltariv_contracts.auth import LoginRequest, LoginResponse
from leltariv_contracts.assets import AssetPage, AssetListItem
from leltariv_contracts.zones import ZoneOut

class ApiClient(Protocol):
    def login(self, request: LoginRequest) -> LoginResponse: ...
    def get_zones(self, token: str) -> list[ZoneOut]: ...
    def get_assets(self, token: str, zone: str | None, q: str | None, page: int, page_size: int) -> AssetPage: ...

class FakeApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def login(self, request: LoginRequest) -> LoginResponse:
        time.sleep(1)
        if request.password != "admin":
            raise ValueError("Hibás e-mail vagy jelszó! (Teszt jelszó: admin)")
        return LoginResponse(
            access_token="fake_token_123",
            refresh_token="fake_refresh_456",
            role="ADMIN",
            display_name="Teszt Elek"
        )

    def get_zones(self, token: str) -> list[ZoneOut]:
        time.sleep(0.3)
        return [
            ZoneOut(id=1, code="261", name="Informatika Tanszék"),
            ZoneOut(id=2, code="262", name="Gépész Tanszék")
        ]

    def get_assets(self, token: str, zone: str | None, q: str | None, page: int, page_size: int) -> AssetPage:
        time.sleep(0.5)
        items = [
            AssetListItem(id=uuid4(), asset_number="3021345", sub_number=0, name="Dell Latitude 5530", zone_code="261", inventory_number="L-1001", quantity=1, activated_on=date(2023, 1, 15), serial_number="SN12345"),
            AssetListItem(id=uuid4(), asset_number="3021346", sub_number=0, name="Irodai szék (kék)", zone_code="261", inventory_number="L-1002", quantity=30, activated_on=date(2020, 5, 10), serial_number=None),
            AssetListItem(id=uuid4(), asset_number="3021347", sub_number=1, name="Oszcilloszkóp", zone_code="262", inventory_number="L-2050", quantity=2, activated_on=date(2019, 9, 1), serial_number="OSZ-99"),
            AssetListItem(id=uuid4(), asset_number="3021348", sub_number=0, name="Tárgyalóasztal", zone_code="262", inventory_number="L-2051", quantity=1, activated_on=None, serial_number=None),
        ]
        if q:
            items = [i for i in items if q.lower() in i.name.lower()]
        if zone and zone != "Mind":
            items = [i for i in items if i.zone_code == zone]
            
        return AssetPage(items=items, total=len(items), page=page, page_size=page_size)