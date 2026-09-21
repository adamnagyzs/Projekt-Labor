from datetime import date
from decimal import Decimal

from scripts.seed import (
    asset_codes_for_seed,
    row_to_seed_asset,
    serial_number_can_be_code,
)


def sample_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Eszköz": "3001540",
        "Alszám": 1,
        "Leltárszám": "005071",
        "Eredeti eszköz": None,
        "Adóhivatal": None,
        "Aktiválás dátuma": 46077,
        "Eszköz megnevezése": "TÁRGYALŐSZÉK",
        "Besz.ért.": 10000,
        "Kum. ÉCS": 2000,
        "K.sz.ért": 8000,
        "Pénznem": "huf",
        "Telephely": "2610000000",
        "Gyártási szám": "SN-001",
        "Mennyiség": 1,
    }
    row.update(overrides)
    return row


def test_row_to_seed_asset_maps_the_required_fields() -> None:
    asset = row_to_seed_asset(sample_row())

    assert asset.asset_number == "3001540"
    assert asset.sub_number == 1
    assert asset.inventory_number == "005071"
    assert asset.zone_code == "261"
    assert asset.activated_on == date(2026, 2, 24)
    assert asset.name_normalized == "targyaloszek"
    assert asset.gross_value == Decimal("10000")
    assert asset.currency == "HUF"
    assert asset.quantity == 1


def test_asset_codes_keep_leading_zero_and_add_meaningful_serial() -> None:
    asset = row_to_seed_asset(sample_row())

    assert asset_codes_for_seed(asset) == [
        ("005071", "LELTARSZAM", True),
        ("3001540", "ESZKOZSZAM", False),
        ("SN-001", "GYARI_SZAM", False),
    ]


def test_invalid_serial_numbers_are_not_seeded_as_asset_codes() -> None:
    for serial_number in ("-", "?", "BÚTOR", "IMÜ-02", "12", None):
        asset = row_to_seed_asset(sample_row(**{"Gyártási szám": serial_number}))

        assert not serial_number_can_be_code(serial_number)
        assert all(code_type != "GYARI_SZAM" for _, code_type, _ in asset_codes_for_seed(asset))

def test_duplicate_codes_on_same_asset_are_seeded_once() -> None:
    asset = row_to_seed_asset(
        sample_row(
            **{
                "Leltárszám": "3038736",
                "Eszköz": "3038736",
                "Gyártási szám": "10299695019948",
            }
        )
    )

    assert asset_codes_for_seed(asset) == [
        ("3038736", "LELTARSZAM", True),
        ("10299695019948", "GYARI_SZAM", False),
    ]