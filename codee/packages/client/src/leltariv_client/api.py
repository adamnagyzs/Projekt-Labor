import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from leltariv_contracts.admin import ImportResult, RestoreResult, SnapshotOut
from leltariv_contracts.assets import (
    AssetDetail,
    AssetListItem,
    AssetPage,
    AssetTypeOut,
    HistoryEntry,
    PersonOut,
    StatusChangeOut,
)
from leltariv_contracts.auth import LoginRequest, LoginResponse
from leltariv_contracts.inventory import (
    ComparisonOut,
    ComparisonRow,
    ComparisonSummary,
    ForeignFind,
    PeriodOut,
    ScanOut,
    SessionOut,
    UnknownCode,
)
from leltariv_contracts.rooms import RoomOut
from leltariv_contracts.zones import ZoneOut

API_PREFIX = "/api/v1"
TIMEOUT_SECONDS = 10.0
LONG_TIMEOUT_SECONDS = 300.0


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
        asset_type_id: int | None = None,
        room_id: UUID | None = None,
        person_id: UUID | None = None,
        status: str | None = None,
    ) -> AssetPage: ...
    def get_asset(self, token: str, asset_id: UUID) -> AssetDetail: ...
    def get_asset_types(self, token: str) -> list[AssetTypeOut]: ...
    def create_asset_type(self, token: str, name: str) -> AssetTypeOut: ...
    def set_asset_type(self, token: str, asset_id: UUID, asset_type_id: int) -> AssetDetail: ...
    def get_persons(self, token: str) -> list[PersonOut]: ...
    def set_responsible(self, token: str, asset_id: UUID, person_id: UUID) -> AssetDetail: ...
    def get_rooms(self, token: str, zone_code: str) -> list[RoomOut]: ...
    def create_room(
        self, token: str, zone_code: str, room_number: str, name: str | None
    ) -> RoomOut: ...
    def start_session(self, token: str, zone_code: str) -> SessionOut: ...
    def post_scan(
        self,
        token: str,
        session_id: UUID,
        raw_code: str,
        quantity: int = 1,
        room_id: UUID | None = None,
    ) -> ScanOut: ...
    def undo_scan(self, token: str, session_id: UUID, scan_id: UUID) -> ScanOut: ...
    def close_session(self, token: str, session_id: UUID) -> SessionOut: ...
    def import_xlsx(self, token: str, path: Path) -> ImportResult: ...
    def get_snapshots(self, token: str) -> list[SnapshotOut]: ...
    def create_snapshot(self, token: str, label: str | None) -> SnapshotOut: ...
    def restore_snapshot(self, token: str, file_name: str) -> RestoreResult: ...
    def get_periods(self, token: str) -> list[PeriodOut]: ...
    def create_period(self, token: str, name: str, year: int) -> PeriodOut: ...
    def close_period(self, token: str, period_id: UUID) -> PeriodOut: ...
    def get_comparison(self, token: str, period_id: UUID, zone_code: str) -> ComparisonOut: ...
    def get_asset_history(self, token: str, asset_id: UUID) -> list[HistoryEntry]: ...
    def change_asset_status(
        self, token: str, asset_id: UUID, status: str, reason: str
    ) -> StatusChangeOut: ...


class HttpApiClient:
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
        content: bytes | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> object:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if content is not None:
            headers["Content-Type"] = "application/octet-stream"

        try:
            response = self._client.request(
                method,
                f"{API_PREFIX}{path}",
                headers=headers,
                json=json,
                params=params,
                content=content,
                timeout=timeout,
            )
        except httpx.RequestError as error:
            raise ValueError(
                f"A szerver nem érhető el ({self.base_url}). Fut a szerver?"
            ) from error

        if response.is_success:
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

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
        asset_type_id: int | None = None,
        room_id: UUID | None = None,
        person_id: UUID | None = None,
        status: str | None = None,
    ) -> AssetPage:
        params: dict[str, str | int] = {"page": page, "page_size": page_size}
        if zone:
            params["zone"] = zone
        if q:
            params["q"] = q
        if main_only:
            params["main_only"] = "true"
        if multi_only:
            params["multi_only"] = "true"
        if field != "mind":
            params["field"] = field
        if asset_type_id is not None:
            params["asset_type_id"] = asset_type_id
        if room_id is not None:
            params["room_id"] = str(room_id)
        if person_id is not None:
            params["person_id"] = str(person_id)
        if status:
            params["status"] = status

        payload = self._request("GET", "/assets", token=token, params=params)
        return AssetPage.model_validate(payload)

    def get_asset(self, token: str, asset_id: UUID) -> AssetDetail:
        payload = self._request("GET", f"/assets/{asset_id}", token=token)
        return AssetDetail.model_validate(payload)

    def get_asset_types(self, token: str) -> list[AssetTypeOut]:
        payload = self._request("GET", "/asset-types", token=token)
        return [AssetTypeOut.model_validate(item) for item in payload]  # type: ignore[union-attr]

    def create_asset_type(self, token: str, name: str) -> AssetTypeOut:
        payload = self._request("POST", "/asset-types", token=token, json={"name": name})
        return AssetTypeOut.model_validate(payload)

    def set_asset_type(self, token: str, asset_id: UUID, asset_type_id: int) -> AssetDetail:
        payload = self._request(
            "PUT", f"/assets/{asset_id}/type", token=token, json={"asset_type_id": asset_type_id}
        )
        return AssetDetail.model_validate(payload)

    def get_persons(self, token: str) -> list[PersonOut]:
        payload = self._request("GET", "/persons", token=token)
        return [PersonOut.model_validate(item) for item in payload]  # type: ignore[union-attr]

    def set_responsible(self, token: str, asset_id: UUID, person_id: UUID) -> AssetDetail:
        payload = self._request(
            "PUT",
            f"/assets/{asset_id}/responsible",
            token=token,
            json={"person_id": str(person_id)},
        )
        return AssetDetail.model_validate(payload)

    def get_rooms(self, token: str, zone_code: str) -> list[RoomOut]:
        payload = self._request("GET", "/rooms", token=token, params={"zone": zone_code})
        return [RoomOut.model_validate(room) for room in payload]  # type: ignore[union-attr]

    def create_room(
        self, token: str, zone_code: str, room_number: str, name: str | None
    ) -> RoomOut:
        body: dict[str, object] = {"zone_code": zone_code, "room_number": room_number}
        if name:
            body["name"] = name
        payload = self._request("POST", "/rooms", token=token, json=body)
        return RoomOut.model_validate(payload)

    def start_session(self, token: str, zone_code: str) -> SessionOut:
        payload = self._request("POST", "/sessions", token=token, json={"zone_code": zone_code})
        return SessionOut.model_validate(payload)

    def post_scan(
        self,
        token: str,
        session_id: UUID,
        raw_code: str,
        quantity: int = 1,
        room_id: UUID | None = None,
    ) -> ScanOut:
        body: dict[str, object] = {"raw_code": raw_code, "quantity": quantity}
        if room_id:
            body["room_id"] = str(room_id)
        payload = self._request("POST", f"/sessions/{session_id}/scans", token=token, json=body)
        return ScanOut.model_validate(payload)

    def undo_scan(self, token: str, session_id: UUID, scan_id: UUID) -> ScanOut:
        payload = self._request("POST", f"/sessions/{session_id}/scans/{scan_id}/undo", token=token)
        return ScanOut.model_validate(payload)

    def close_session(self, token: str, session_id: UUID) -> SessionOut:
        payload = self._request("POST", f"/sessions/{session_id}/close", token=token)
        return SessionOut.model_validate(payload)

    def import_xlsx(self, token: str, path: Path) -> ImportResult:
        payload = self._request(
            "POST",
            "/imports",
            token=token,
            params={"file_name": path.name},
            content=path.read_bytes(),
            timeout=LONG_TIMEOUT_SECONDS,
        )
        return ImportResult.model_validate(payload)

    def get_snapshots(self, token: str) -> list[SnapshotOut]:
        payload = self._request("GET", "/snapshots", token=token)
        return [SnapshotOut.model_validate(item) for item in payload]  # type: ignore[union-attr]

    def create_snapshot(self, token: str, label: str | None) -> SnapshotOut:
        payload = self._request(
            "POST", "/snapshots", token=token, json={"label": label}, timeout=LONG_TIMEOUT_SECONDS
        )
        return SnapshotOut.model_validate(payload)

    def restore_snapshot(self, token: str, file_name: str) -> RestoreResult:
        payload = self._request(
            "POST",
            f"/snapshots/{quote(file_name)}/restore",
            token=token,
            timeout=LONG_TIMEOUT_SECONDS,
        )
        return RestoreResult.model_validate(payload)

    def get_periods(self, token: str) -> list[PeriodOut]:
        payload = self._request("GET", "/periods", token=token)
        return [PeriodOut.model_validate(item) for item in payload]  # type: ignore[union-attr]

    def create_period(self, token: str, name: str, year: int) -> PeriodOut:
        payload = self._request("POST", "/periods", token=token, json={"name": name, "year": year})
        return PeriodOut.model_validate(payload)

    def close_period(self, token: str, period_id: UUID) -> PeriodOut:
        payload = self._request("POST", f"/periods/{period_id}/close", token=token)
        return PeriodOut.model_validate(payload)

    def get_comparison(self, token: str, period_id: UUID, zone_code: str) -> ComparisonOut:
        payload = self._request(
            "GET", f"/periods/{period_id}/comparison", token=token, params={"zone_code": zone_code}
        )
        return ComparisonOut.model_validate(payload)

    def get_asset_history(self, token: str, asset_id: UUID) -> list[HistoryEntry]:
        payload = self._request("GET", f"/assets/{asset_id}/history", token=token)
        return [HistoryEntry.model_validate(item) for item in payload]  # type: ignore[union-attr]

    def change_asset_status(
        self, token: str, asset_id: UUID, status: str, reason: str
    ) -> StatusChangeOut:
        payload = self._request(
            "PATCH",
            f"/assets/{asset_id}/status",
            token=token,
            json={"status": status, "reason": reason},
        )
        return StatusChangeOut.model_validate(payload)


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
        asset_type="Számítógép",
        responsible="Kovács Anna",
        status="ACTIVE",
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
        asset_type="Bútor",
        responsible=None,
        status="ACTIVE",
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
        asset_type="Egyéb",
        responsible="Nagy Béla",
        status="ACTIVE",
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
        asset_type="Bútor",
        responsible=None,
        status="ACTIVE",
    ),
]


class FakeApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self._session_zones: dict[UUID, str] = {}
        self._asset_types = [
            AssetTypeOut(id=1, name="Bútor"),
            AssetTypeOut(id=2, name="Számítógép"),
            AssetTypeOut(id=3, name="Egyéb"),
        ]
        self._persons = [
            PersonOut(id=uuid4(), name="Kovács Anna", org_unit="IK"),
            PersonOut(id=uuid4(), name="Nagy Béla", org_unit="MK"),
        ]
        self._rooms = {
            "261": [
                RoomOut(
                    id=uuid4(),
                    zone_code="261",
                    room_number="I-101",
                    name="Iroda",
                    label="I-101 · Iroda",
                ),
            ],
            "262": [
                RoomOut(
                    id=uuid4(),
                    zone_code="262",
                    room_number="G-202",
                    name="Labor",
                    label="G-202 · Labor",
                ),
            ],
        }
        self._periods = [
            PeriodOut(
                id=uuid4(),
                name="2026. évi leltár",
                year=2026,
                state="ACTIVE",
                opened_at=datetime.now(UTC),
                closed_at=None,
            )
        ]
        self._statuses: dict[UUID, str] = {asset.id: "ACTIVE" for asset in FAKE_ASSETS}
        self._histories: dict[UUID, list[HistoryEntry]] = {
            asset.id: [
                HistoryEntry(
                    at=datetime.now(UTC),
                    kind="CREATED",
                    text=f"Létrehozva: {asset.name}",
                    by="Teszt Elek",
                    period="2026. évi leltár",
                )
            ]
            for asset in FAKE_ASSETS
        }

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
        asset_type_id: int | None = None,
        room_id: UUID | None = None,
        person_id: UUID | None = None,
        status: str | None = None,
    ) -> AssetPage:
        time.sleep(0.5)
        items = []
        for asset in FAKE_ASSETS:
            cur_status = self._statuses.get(asset.id, "ACTIVE")
            # Frissítjük a status mezőt a listaelemben
            item = asset.model_copy(update={"status": cur_status})  # type: ignore
            items.append(item)

        if status:
            items = [i for i in items if i.status == status]
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
        cur_status = self._statuses.get(asset_id, "ACTIVE")
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
            asset_type_id=1,
            room=None,
            responsible=None,
            status=cur_status,  # type: ignore
        )

    def get_asset_types(self, token: str) -> list[AssetTypeOut]:
        time.sleep(0.2)
        return self._asset_types

    def create_asset_type(self, token: str, name: str) -> AssetTypeOut:
        time.sleep(0.2)
        if any(t.name.lower() == name.lower() for t in self._asset_types):
            raise ValueError("Ilyen nevű típus már van.")
        new_type = AssetTypeOut(id=len(self._asset_types) + 1, name=name)
        self._asset_types.append(new_type)
        return new_type

    def set_asset_type(self, token: str, asset_id: UUID, asset_type_id: int) -> AssetDetail:
        time.sleep(0.2)
        return self.get_asset(token, asset_id)

    def get_persons(self, token: str) -> list[PersonOut]:
        time.sleep(0.2)
        return self._persons

    def set_responsible(self, token: str, asset_id: UUID, person_id: UUID) -> AssetDetail:
        time.sleep(0.2)
        return self.get_asset(token, asset_id)

    def get_rooms(self, token: str, zone_code: str) -> list[RoomOut]:
        time.sleep(0.2)
        return self._rooms.get(zone_code, [])

    def create_room(
        self, token: str, zone_code: str, room_number: str, name: str | None
    ) -> RoomOut:
        time.sleep(0.2)
        new_room = RoomOut(
            id=uuid4(),
            zone_code=zone_code,
            room_number=room_number,
            name=name,
            label=f"{room_number} · {name}" if name else room_number,
        )
        self._rooms.setdefault(zone_code, []).append(new_room)
        return new_room

    def start_session(self, token: str, zone_code: str) -> SessionOut:
        time.sleep(0.2)
        session_id = uuid4()
        self._session_zones[session_id] = zone_code
        return SessionOut(
            id=session_id,
            zone_code=zone_code,
            period_name="2026. évi leltár",
            started_at=datetime.now(UTC),
            closed_at=None,
        )

    def post_scan(
        self,
        token: str,
        session_id: UUID,
        raw_code: str,
        quantity: int = 1,
        room_id: UUID | None = None,
    ) -> ScanOut:
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
            result=result,  # type: ignore[arg-type]
            scanned_at=datetime.now(UTC),
            asset=asset,
            message=message,
            quantity=quantity,
            room=None,
            expected=asset.quantity if asset else None,
            counted=quantity if asset else None,
            compensates_scan_id=None,
        )

    def undo_scan(self, token: str, session_id: UUID, scan_id: UUID) -> ScanOut:
        time.sleep(0.1)
        return ScanOut(
            id=uuid4(),
            raw_code="L-1001",
            result="FOUND",
            scanned_at=datetime.now(UTC),
            asset=None,
            message="Visszavonva: L-1001, 1 db.",
            quantity=-1,
            room=None,
            compensates_scan_id=scan_id,
        )

    def close_session(self, token: str, session_id: UUID) -> SessionOut:
        time.sleep(0.2)
        return SessionOut(
            id=session_id,
            zone_code="261",
            period_name="2026. évi leltár",
            started_at=datetime.now(UTC),
            closed_at=datetime.now(UTC),
        )

    def get_periods(self, token: str) -> list[PeriodOut]:
        time.sleep(0.2)
        return self._periods

    def create_period(self, token: str, name: str, year: int) -> PeriodOut:
        time.sleep(0.2)
        new_p = PeriodOut(
            id=uuid4(),
            name=name,
            year=year,
            state="ACTIVE",
            opened_at=datetime.now(UTC),
            closed_at=None,
        )
        self._periods.insert(0, new_p)
        return new_p

    def close_period(self, token: str, period_id: UUID) -> PeriodOut:
        time.sleep(0.2)
        for p in self._periods:
            if p.id == period_id:
                return PeriodOut(
                    id=p.id,
                    name=p.name,
                    year=p.year,
                    state="CLOSED",
                    opened_at=p.opened_at,
                    closed_at=datetime.now(UTC),
                )
        raise PeriodOut  # type: ignore

    def get_comparison(self, token: str, period_id: UUID, zone_code: str) -> ComparisonOut:
        time.sleep(0.3)
        zone_assets = [a for a in FAKE_ASSETS if a.zone_code == zone_code]
        rows = []
        found_cnt = 0
        missing_cnt = 0

        for idx, asset in enumerate(zone_assets):
            if idx == 0:
                cat = "FOUND"
                exp = asset.quantity
                cnt = asset.quantity
                found_cnt += 1
            elif idx == 1:
                cat = "PARTIAL"
                exp = asset.quantity
                cnt = max(0, asset.quantity - 1)
                found_cnt += 1
            else:
                cat = "MISSING"
                exp = asset.quantity
                cnt = 0
                missing_cnt += 1

            rows.append(
                ComparisonRow(
                    asset=asset,
                    status=self._statuses.get(asset.id, "ACTIVE"),  # type: ignore
                    expected=exp,
                    counted=cnt,
                    difference=cnt - exp,
                    category=cat,  # type: ignore
                    verification="DIRECT" if cnt > 0 else None,
                    room="I-101",
                    found_in_zone=None,
                )
            )

        summary = ComparisonSummary(
            expected_assets=len(zone_assets),
            found=found_cnt,
            inherited=0,
            partial=1 if len(zone_assets) > 1 else 0,
            missing=missing_cnt,
            surplus=0,
            foreign=1,
            unknown=1,
            progress_percent=float(found_cnt) / max(1, len(zone_assets)) * 100.0,
        )

        foreign_finds = [
            ForeignFind(
                asset=FAKE_ASSETS[0],
                home_zone_code="261",
                quantity=1,
                room="G-202",
            )
        ]
        unknown_codes = [
            UnknownCode(
                raw_code="UNKNOWN-999",
                quantity=1,
                room="G-202",
            )
        ]

        period = next((p for p in self._periods if p.id == period_id), self._periods[0])
        return ComparisonOut(
            period=period,
            zone_code=zone_code,
            summary=summary,
            rows=rows,
            foreign=foreign_finds,
            unknown=unknown_codes,
        )

    def get_asset_history(self, token: str, asset_id: UUID) -> list[HistoryEntry]:
        time.sleep(0.2)
        if asset_id in self._histories:
            return self._histories[asset_id]
        return [
            HistoryEntry(
                at=datetime.now(UTC),
                kind="CREATED",
                text="Eszköz rögzítve a rendszerben.",
                by="Teszt Elek",
                period="2026. évi leltár",
            )
        ]

    def change_asset_status(
        self, token: str, asset_id: UUID, status: str, reason: str
    ) -> StatusChangeOut:
        time.sleep(0.2)
        old_status = self._statuses.get(asset_id, "ACTIVE")
        self._statuses[asset_id] = status

        entry = HistoryEntry(
            at=datetime.now(UTC),
            kind="STATUS",
            text=f"Állapot: {old_status} → {status}. Indoklás: {reason}",
            by="Teszt Elek",
            period="2026. évi leltár",
        )
        self._histories.setdefault(asset_id, []).insert(0, entry)

        return StatusChangeOut(
            id=uuid4(),
            asset_id=asset_id,
            old_status=old_status,  # type: ignore
            new_status=status,  # type: ignore
            reason=reason,
            changed_at=datetime.now(UTC),
            changed_by="Teszt Elek",
        )