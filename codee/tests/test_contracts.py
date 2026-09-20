from datetime import date
from uuid import uuid4

from leltariv_contracts import AssetPage, LoginResponse
from leltariv_contracts.assets import AssetListItem


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
