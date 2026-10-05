import time
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from leltariv_contracts.assets import AssetDetail, AssetListItem, AssetPage
from leltariv_contracts.auth import LoginRequest, LoginResponse
from leltariv_contracts.inventory import ScanOut, SessionOut
from leltariv_contracts.zones import ZoneOut

API_PREFIX = "/api/v1"
TIMEOUT_SECONDS = 10.0


class ApiClient(Protocol):
    def login(self, request: LoginRequest) -> LoginResponse: ...
    def get_zones(self, token: str) -> list[ZoneOut]: ...
    def get_assets(
        self,
        token: str,
        zone: str | None,
        q: str | None,
        page: int,
        page_size: int,
        main_only: bool = False,
        multi_only: bool = False,
        field: str = "mind",
    ) -> AssetPage: ...
    def get_asset(self, token: str, asset_id: UUID) -> AssetDetail: ...
    def start_session(self, token: str, zone_code: str) -> SessionOut: ...
    def post_scan(self, token: str, session_id: UUID, raw_code: str) -> ScanOut: ...


class HttpApiClient:
    """A valódi szerverrel beszélő kliens.

    A válaszokat ugyanazokba a Pydantic modellekbe olvassuk be, amikkel a szerver
    validál, tehát ha a szerződés megváltozik, az itt derül ki, nem a felületen.

    Minden metódus `ValueError`-t dob a felhasználónak szánt üzenettel; a hívó
    munkaszál ezt fogja meg és jeleníti meg. Hálózati kód nem kerül a UI szálra.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=TIMEOUT_SECONDS)

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: dict[str, object] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> object:
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        try:
            response = self._client.request(
                method, f"{API_PREFIX}{path}", headers=headers, json=json, params=params
            )
        except httpx.RequestError as error:
            raise ValueError(
                f"A szerver nem érhető el ({self.base_url}). Fut a szerver?"
            ) from error

        if response.is_success:
            return response.json()

        # A FastAPI hibaválasza {"detail": "..."} — ha mégsem az jön, a státuszt mutatjuk.
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None

        raise ValueError(
            str(detail) if detail else f"A szerver hibát adott: {response.status_code}"
        )

    def login(self, request: LoginRequest) -> LoginResponse:
        payload = self._request("POST", "/auth/login", json=request.model_dump())
        return LoginResponse.model_validate(payload)

    def get_zones(self, token: str) -> list[ZoneOut]:
        payload = self._request("GET", "/zones", token=token)
        return [ZoneOut.model_validate(zone) for zone in payload]  # type: ignore[union-attr]

    def get_assets(
        self,
        token: str,
        zone: str | None,
        q: str | None,
        page: int,
        page_size: int,
        main_only: bool = False,
        multi_only: bool = False,
        field: str = "mind",
    ) -> AssetPage:
        params: dict[str, str | int] = {"page": page, "page_size": page_size}
        if zone:
            params["zone"] = zone
        if q:
            params["q"] = q
        # Csak a bekapcsolt szűrő megy át; a szerver alapértéke amúgy is false.
        if main_only:
            params["main_only"] = "true"
        if multi_only:
            params["multi_only"] = "true"
        if field != "mind":
            params["field"] = field

        payload = self._request("GET", "/assets", token=token, params=params)
        return AssetPage.model_validate(payload)

    def get_asset(self, token: str, asset_id: UUID) -> AssetDetail:
        payload = self._request("GET", f"/assets/{asset_id}", token=token)
        return AssetDetail.model_validate(payload)

    def start_session(self, token: str, zone_code: str) -> SessionOut:
        payload = self._request("POST", "/sessions", token=token, json={"zone_code": zone_code})
        return SessionOut.model_validate(payload)

    def post_scan(self, token: str, session_id: UUID, raw_code: str) -> ScanOut:
        payload = self._request(
            "POST", f"/sessions/{session_id}/scans", token=token, json={"raw_code": raw_code}
        )
        return ScanOut.model_validate(payload)


#: a hamis kliens állománya; a leltárszámok szándékosan körzetenként különböznek
FAKE_ASSETS = [
    AssetListItem(
        id=uuid4(),
        asset_number="3021345",
        sub_number=0,
        name="Dell Latitude 5530",
        zone_code="261",
        inventory_number="L-1001",
        quantity=1,
        activated_on=date(2023, 1, 15),
        serial_number="SN12345",
    ),
    AssetListItem(
        id=uuid4(),
        asset_number="3021346",
        sub_number=0,
        name="Irodai szék (kék)",
        zone_code="261",
        inventory_number="L-1002",
        quantity=30,
        activated_on=date(2020, 5, 10),
        serial_number=None,
    ),
    AssetListItem(
        id=uuid4(),
        asset_number="3021347",
        sub_number=1,
        name="Oszcilloszkóp",
        zone_code="262",
        inventory_number="L-2050",
        quantity=2,
        activated_on=date(2019, 9, 1),
        serial_number="OSZ-99",
    ),
    AssetListItem(
        id=uuid4(),
        asset_number="3021348",
        sub_number=0,
        name="Tárgyalóasztal",
        zone_code="262",
        inventory_number="L-2051",
        quantity=1,
        activated_on=None,
        serial_number=None,
    ),
]


class FakeApiClient:
    """Szerver nélküli kliens a felület kipróbálásához; a szerver szabályait utánozza."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._session_zones: dict[UUID, str] = {}

    def login(self, request: LoginRequest) -> LoginResponse:
        time.sleep(1)
        if request.password != "admin":
            raise ValueError("Hibás e-mail vagy jelszó! (Teszt jelszó: admin)")
        return LoginResponse(
            access_token="fake_token_123",
            refresh_token="fake_refresh_456",
            role="ADMIN",
            display_name="Teszt Elek",
        )

    def get_zones(self, token: str) -> list[ZoneOut]:
        time.sleep(0.3)
        return [
            ZoneOut(id=1, code="261", name="Informatika Tanszék"),
            ZoneOut(id=2, code="262", name="Gépész Tanszék"),
        ]

    def get_assets(
        self,
        token: str,
        zone: str | None,
        q: str | None,
        page: int,
        page_size: int,
        main_only: bool = False,
        multi_only: bool = False,
        field: str = "mind",
    ) -> AssetPage:
        time.sleep(0.5)
        items = FAKE_ASSETS
        if q:
            items = [i for i in items if q.lower() in i.name.lower()]
        if zone:
            items = [i for i in items if i.zone_code == zone]
        if main_only:
            items = [i for i in items if i.sub_number == 0]
        if multi_only:
            items = [i for i in items if i.quantity > 1]

        return AssetPage(items=items, total=len(items), page=page, page_size=page_size)

    def get_asset(self, token: str, asset_id: UUID) -> AssetDetail:
        time.sleep(0.3)
        item = next((i for i in FAKE_ASSETS if i.id == asset_id), None)
        if item is None:
            raise ValueError("A megadott eszköz nem található.")
        return AssetDetail(
            id=item.id,
            asset_number=item.asset_number,
            sub_number=item.sub_number,
            name=item.name,
            zone_code=item.zone_code,
            quantity=item.quantity,
            activated_on=item.activated_on,
            serial_number=item.serial_number,
            codes=[],
            accessories=[],
        )

    def start_session(self, token: str, zone_code: str) -> SessionOut:
        time.sleep(0.2)
        session_id = uuid4()
        self._session_zones[session_id] = zone_code
        return SessionOut(
            id=session_id,
            zone_code=zone_code,
            period_name="2026. évi leltár",
            started_at=datetime.now(UTC),
        )

    def post_scan(self, token: str, session_id: UUID, raw_code: str) -> ScanOut:
        time.sleep(0.1)
        active_zone = self._session_zones.get(session_id)
        if active_zone is None:
            raise ValueError("A megadott munkamenet nem található.")

        asset = next((i for i in FAKE_ASSETS if i.inventory_number == raw_code), None)
        if asset is None:
            result, message = (
                "UNKNOWN_CODE",
                f"Ismeretlen kód: {raw_code}. Rögzítettük, de nem tartozik hozzá eszköz.",
            )
        elif asset.zone_code == active_zone:
            result, message = "FOUND", f"Rendben: {asset.name}."
        else:
            result, message = (
                "FOREIGN_ZONE",
                f"Idegen körzet: {asset.name} a(z) {asset.zone_code} körzetben van nyilvántartva.",
            )

        return ScanOut(
            id=uuid4(),
            raw_code=raw_code,
            result=result,
            scanned_at=datetime.now(UTC),
            asset=asset,
            message=message,
        )
