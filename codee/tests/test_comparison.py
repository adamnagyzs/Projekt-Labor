from datetime import UTC, datetime, timedelta
from typing import get_args

from leltariv_contracts import assets, inventory
from leltariv_domain import comparison
from leltariv_domain.comparison import (
    StatusChange,
    classify,
    expected_quantity,
    progress_percent,
    status_at,
)
from leltariv_server.api.history import scan_text, status_text

T0 = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


def test_values_match_contract() -> None:
    assert get_args(comparison.AssetStatus) == get_args(assets.AssetStatus)
    assert get_args(comparison.Category) == get_args(inventory.ComparisonCategory)
    assert get_args(comparison.Verification) == get_args(inventory.Verification)
    assert set(assets.STATUS_LABELS) == set(get_args(assets.AssetStatus))


def test_classify_by_quantity() -> None:
    assert classify(expected=1, counted=1) == ("FOUND", "DIRECT")
    assert classify(expected=30, counted=27) == ("PARTIAL", "DIRECT")
    assert classify(expected=30, counted=0) == ("MISSING", None)
    assert classify(expected=30, counted=32) == ("SURPLUS", "DIRECT")


def test_inactive_asset_found_is_surplus() -> None:
    assert classify(expected=0, counted=1) == ("SURPLUS", "DIRECT")


def test_accessory_inherits_from_found_parent() -> None:
    assert classify(expected=1, counted=0, parent_counted=1) == ("FOUND", "INHERITED")
    # a főeszköz sincs meg: a tartozék is hiányzik
    assert classify(expected=1, counted=0, parent_counted=0) == ("MISSING", None)
    # saját beolvasás mindig erősebb, mint a főeszközé
    assert classify(expected=1, counted=1, parent_counted=1) == ("FOUND", "DIRECT")


def test_expected_quantity_only_for_active() -> None:
    assert expected_quantity("ACTIVE", 30) == 30
    for status in ("SCRAPPED", "LOST", "STOLEN", "OTHER"):
        assert expected_quantity(status, 30) == 0


def test_status_at_rebuilds_earlier_state() -> None:
    changes = [
        StatusChange(T0 + timedelta(days=1), "ACTIVE", "LOST"),
        StatusChange(T0 + timedelta(days=3), "LOST", "ACTIVE"),
        StatusChange(T0 + timedelta(days=5), "ACTIVE", "SCRAPPED"),
    ]
    assert status_at("SCRAPPED", changes, T0) == "ACTIVE"
    assert status_at("SCRAPPED", changes, T0 + timedelta(days=2)) == "LOST"
    assert status_at("SCRAPPED", changes, T0 + timedelta(days=4)) == "ACTIVE"
    assert status_at("SCRAPPED", changes, T0 + timedelta(days=6)) == "SCRAPPED"
    assert status_at("ACTIVE", [], T0) == "ACTIVE"


def test_progress_percent() -> None:
    assert progress_percent(expected_assets=4, missing=1) == 75.0
    assert progress_percent(expected_assets=3, missing=1) == 66.7
    assert progress_percent(expected_assets=0, missing=0) == 100.0


def test_history_texts() -> None:
    assert (
        status_text("ACTIVE", "SCRAPPED", "Eltört")
        == "Állapot: Aktív → Selejtezett. Indoklás: Eltört"
    )
    assert scan_text("FOUND", 3, "262", "G-210 · Labor") == (
        "Beolvasva a(z) 262 körzetben, G-210 · Labor: 3 db."
    )
    assert scan_text("SURPLUS", 1, "262", None) == "Többletként beolvasva a(z) 262 körzetben: 1 db."
    assert scan_text("FOREIGN_ZONE", 1, "261", None) == (
        "Idegen körzetben beolvasva, a(z) 261 körzetben: 1 db."
    )
    assert (
        scan_text("FOUND", -3, "262", None) == "Beolvasás visszavonva: 3 db (a(z) 262 körzetben)."
    )
