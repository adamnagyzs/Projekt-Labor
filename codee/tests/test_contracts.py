from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from leltariv_contracts import AssetDetail, AssetPage, LoginResponse, ScanCreate, ScanOut
from leltariv_contracts.assets import AssetCodeOut, AssetListItem
from pydantic import ValidationError


def test_asset_page_roundtrip() -> None:
    page = AssetPage(
        items=[
            AssetListItem(
                id=uuid4(),
                asset_number="3021345",
                sub_number=0,
                name="SZÉK (SFERA KARFÁSSZÉK)",
                zone_code="261",
                inventory_number="024540",
                quantity=1,
                activated_on=date(2021, 7, 15),
                serial_number=None,
            )
        ],
        total=1,
        page=1,
        page_size=50,
    )
    parsed = AssetPage.model_validate_json(page.model_dump_json())
    assert parsed.items[0].inventory_number == "024540"


def test_leading_zero_survives() -> None:
    """554 tétel leltárszáma vezető nullás — ez nem alakulhat számmá."""
    item = AssetPage.model_validate(
        {
            "items": [
                {
                    "id": str(uuid4()),
                    "asset_number": "102057",
                    "sub_number": 0,
                    "name": "SZÉK",
                    "zone_code": "261",
                    "inventory_number": "005071",
                    "quantity": 1,
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 50,
        }
    ).items[0]
    assert item.inventory_number == "005071"


def test_role_is_constrained() -> None:
    resp = LoginResponse(
        access_token="x", refresh_token="y", role="LELTAROZO", display_name="Teszt"
    )
    assert resp.role == "LELTAROZO"


def test_asset_detail_roundtrip() -> None:
    accessory = AssetListItem(
        id=uuid4(), asset_number="3021345", sub_number=1, name="MONITOR", zone_code="262"
    )
    detail = AssetDetail(
        id=uuid4(),
        asset_number="3021345",
        sub_number=0,
        name="SZÁMÍTÓGÉP",
        zone_code="262",
        quantity=1,
        codes=[AssetCodeOut(code="024540", code_type="LELTARSZAM", is_primary=True)],
        accessories=[accessory],
    )
    parsed = AssetDetail.model_validate_json(detail.model_dump_json())
    assert parsed.codes[0].code == "024540"
    assert parsed.accessories[0].sub_number == 1


def test_scan_out_roundtrip_without_asset() -> None:
    scan = ScanOut(
        id=uuid4(),
        raw_code="X123",
        result="UNKNOWN_CODE",
        scanned_at=datetime.now(UTC),
        message="Ismeretlen kód: X123. Rögzítettük, de nem tartozik hozzá eszköz.",
    )
    parsed = ScanOut.model_validate_json(scan.model_dump_json())
    assert parsed.asset is None
    assert parsed.result == "UNKNOWN_CODE"


def test_empty_scan_code_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScanCreate(raw_code="")
