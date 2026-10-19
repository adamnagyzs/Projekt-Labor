from typing import get_args
from uuid import uuid4

from leltariv_contracts import inventory
from leltariv_domain import scanning
from leltariv_domain.scanning import CodeMatch, count_result, resolve, scan_message, undo_message


def test_result_values_match_contract() -> None:
    assert get_args(scanning.ScanResult) == get_args(inventory.ScanResult)


def test_no_match_is_unknown() -> None:
    assert resolve([], "262") == ("UNKNOWN_CODE", None)


def test_active_zone_wins_over_foreign() -> None:
    # A 024540 mindkét körzetben szerepel; a 262-es munkamenetben a 262-es eszköz kell.
    in_261 = CodeMatch(asset_id=uuid4(), zone_code="261")
    in_262 = CodeMatch(asset_id=uuid4(), zone_code="262")

    assert resolve([in_261, in_262], "262") == ("FOUND", in_262.asset_id)
    assert resolve([in_262, in_261], "261") == ("FOUND", in_261.asset_id)


def test_single_foreign_match_keeps_asset() -> None:
    in_261 = CodeMatch(asset_id=uuid4(), zone_code="261")

    assert resolve([in_261], "262") == ("FOREIGN_ZONE", in_261.asset_id)


def test_ambiguous_foreign_match_has_no_asset() -> None:
    matches = [CodeMatch(asset_id=uuid4(), zone_code="261"), CodeMatch(uuid4(), "263")]

    assert resolve(matches, "262") == ("FOREIGN_ZONE", None)


def test_messages() -> None:
    assert (
        scan_message("FOUND", raw_code="024540", asset_name="Szék", asset_zone_code="262")
        == "Rendben: Szék."
    )
    assert (
        scan_message("FOREIGN_ZONE", raw_code="024540", asset_name="Szék", asset_zone_code="261")
        == "Idegen körzet: Szék a(z) 261 körzetben van nyilvántartva."
    )
    assert (
        scan_message("FOREIGN_ZONE", raw_code="024540", asset_name=None, asset_zone_code=None)
        == "Idegen körzet: a(z) 024540 kód több másik körzetben is szerepel."
    )
    assert (
        scan_message("UNKNOWN_CODE", raw_code="X123", asset_name=None, asset_zone_code=None)
        == "Ismeretlen kód: X123. Rögzítettük, de nem tartozik hozzá eszköz."
    )


def test_count_within_expected_is_found() -> None:
    assert count_result(expected=30, counted_before=27, quantity=3) == "FOUND"


def test_count_over_expected_is_surplus() -> None:
    assert count_result(expected=30, counted_before=30, quantity=1) == "SURPLUS"
    # egy beolvasáson belül is át lehet lépni a nyilvántartottat
    assert count_result(expected=30, counted_before=28, quantity=5) == "SURPLUS"


def test_single_item_scanned_twice_is_surplus() -> None:
    assert count_result(expected=1, counted_before=0, quantity=1) == "FOUND"
    assert count_result(expected=1, counted_before=1, quantity=1) == "SURPLUS"


def test_quantity_messages() -> None:
    def found(counted: int) -> str:
        return scan_message(
            "FOUND",
            raw_code="1",
            asset_name="Szék",
            asset_zone_code="262",
            expected=30,
            counted=counted,
        )

    assert found(27) == "Rendben: Szék. 27/30 db, hiányzik 3."
    assert found(30) == "Rendben: Szék. Megvan mind a(z) 30 db."
    assert (
        scan_message(
            "SURPLUS",
            raw_code="1",
            asset_name="Szék",
            asset_zone_code="262",
            expected=30,
            counted=32,
        )
        == "Többlet: Szék. 32 db a nyilvántartott 30 helyett. Ha tévedés, vond vissza."
    )
    assert undo_message("024540", 5) == "Visszavonva: 024540, 5 db."
