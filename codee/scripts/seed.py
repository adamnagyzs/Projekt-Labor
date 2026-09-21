from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from leltariv_domain.normalization import (
    is_meaningful_serial_number,
    normalize_code,
    normalize_text,
)
from leltariv_domain.xlsx_import import (
    as_source_text,
    excel_serial_to_date,
    zone_code_from_site,
)


@dataclass(frozen=True)
class SeedAsset:
    asset_number: str
    sub_number: int
    inventory_number: str | None
    original_asset: str | None
    tax_ref: str | None
    activated_on: date | None
    name: str
    name_normalized: str
    gross_value: Decimal | None
    accum_depreciation: Decimal | None
    book_value: Decimal | None
    currency: str
    site_code: str
    zone_code: str
    serial_number: str | None
    quantity: int


def required_source_text(row: Mapping[str, object], column: str) -> str:
    """Kötelező SAP mező szöveges értéke."""
    value = as_source_text(row.get(column))
    if value is None:
        raise ValueError(f"Hiányzó kötelező mező: {column}")

    return value


def optional_source_text(row: Mapping[str, object], column: str) -> str | None:
    """Opcionális SAP mező szöveges értéke."""
    return as_source_text(row.get(column))


def to_int(value: object, field_name: str) -> int:
    """SAP számmezőt egész számmá alakít."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} nem lehet logikai érték.")

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    text_value = as_source_text(value)
    if text_value is None:
        raise ValueError(f"Hiányzó vagy érvénytelen egész érték: {field_name}")

    try:
        return int(text_value)
    except ValueError as error:
        raise ValueError(f"Érvénytelen egész érték: {field_name}={value!r}") from error


def to_decimal(value: object) -> Decimal | None:
    """SAP pénzügyi értéket Decimal-lá alakít."""
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        raise ValueError("A pénzügyi érték nem lehet logikai érték.")

    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"Érvénytelen pénzügyi érték: {value!r}") from error


def row_to_seed_asset(row: Mapping[str, object]) -> SeedAsset:
    """SAP XLSX-sorból adatbázis-seedhez használható eszköz-adatot készít."""
    asset_number = required_source_text(row, "Eszköz")
    sub_number = to_int(row.get("Alszám"), "Alszám")
    inventory_number = optional_source_text(row, "Leltárszám")
    original_asset = optional_source_text(row, "Eredeti eszköz")
    tax_ref = optional_source_text(row, "Adóhivatal")
    activated_on = excel_serial_to_date(row.get("Aktiválás dátuma"))
    name = required_source_text(row, "Eszköz megnevezése")
    site_code = required_source_text(row, "Telephely")
    serial_number = optional_source_text(row, "Gyártási szám")

    raw_currency = optional_source_text(row, "Pénznem")
    currency = normalize_code(raw_currency) if raw_currency else "HUF"

    return SeedAsset(
        asset_number=asset_number,
        sub_number=sub_number,
        inventory_number=inventory_number,
        original_asset=original_asset,
        tax_ref=tax_ref,
        activated_on=activated_on,
        name=name,
        name_normalized=normalize_text(name),
        gross_value=to_decimal(row.get("Besz.ért.")),
        accum_depreciation=to_decimal(row.get("Kum. ÉCS")),
        book_value=to_decimal(row.get("K.sz.ért")),
        currency=currency,
        site_code=site_code,
        zone_code=zone_code_from_site(site_code),
        serial_number=serial_number,
        quantity=to_int(row.get("Mennyiség"), "Mennyiség"),
    )


def serial_number_can_be_code(serial_number: str | None) -> bool:
    """A gyári szám asset_code-ként való felvételének szabálya."""
    return is_meaningful_serial_number(serial_number)


def asset_codes_for_seed(asset: SeedAsset) -> list[tuple[str, str, bool]]:
    """Az eszközhöz tartozó kereshető kódok: (kód, típus, elsődleges)."""
    codes: list[tuple[str, str, bool]] = []

    if asset.inventory_number is not None:
        codes.append((asset.inventory_number, "LELTARSZAM", True))

    codes.append((asset.asset_number, "ESZKOZSZAM", False))

    if serial_number_can_be_code(asset.serial_number):
        assert asset.serial_number is not None
        codes.append((asset.serial_number, "GYARI_SZAM", False))

    return codes