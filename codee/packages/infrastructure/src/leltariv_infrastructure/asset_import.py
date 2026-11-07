"""SAP-eszközlista (XLSX) betöltése az adatbázisba.

A seed-szkript és a szerver importvégpontja is ezt használja, hogy a két út ne térjen el.
Ami már az adatbázisban van (ugyanaz az eszközszám és alszám), azt nem írja felül, csak
megszámolja: így ugyanaz a fájl kétszer is beolvasható kár nélkül.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import IO
from uuid import uuid4

from leltariv_domain.categories import suggest_type
from leltariv_domain.normalization import (
    is_meaningful_serial_number,
    normalize_code,
    normalize_text,
)
from leltariv_domain.xlsx_import import (
    as_source_text,
    excel_serial_to_date,
    read_asset_rows,
    zone_code_from_site,
)
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from leltariv_infrastructure.db.models import (
    Asset,
    AssetCode,
    AssetType,
    ImportBatch,
    InventoryZone,
)

ZONE_NAMES = {
    "261": "Leltárkörzet 261",
    "262": "Leltárkörzet 262",
}


@dataclass(frozen=True)
class SourceAsset:
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


@dataclass
class ImportReport:
    rows_read: int = 0
    rows_ok: int = 0
    #: már az adatbázisban lévő eszközök; ezeket a betöltés nem módosítja
    rows_skipped: int = 0
    rows_failed: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list[tuple[int, str]])


def required_source_text(row: Mapping[str, object], column: str) -> str:
    value = as_source_text(row.get(column))
    if value is None:
        raise ValueError(f"Hiányzó kötelező mező: {column}")
    return value


def optional_source_text(row: Mapping[str, object], column: str) -> str | None:
    return as_source_text(row.get(column))


def to_int(value: object, field_name: str) -> int:
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
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("A pénzügyi érték nem lehet logikai érték.")

    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"Érvénytelen pénzügyi érték: {value!r}") from error


def row_to_source_asset(row: Mapping[str, object]) -> SourceAsset:
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

    return SourceAsset(
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
    return is_meaningful_serial_number(serial_number)


def asset_codes_for(asset: SourceAsset) -> list[tuple[str, str, bool]]:
    """Kereshető, zónán belül egyedi kódok: kód, típus, elsődleges-e."""
    codes: list[tuple[str, str, bool]] = []
    seen_normalized_codes: set[str] = set()

    def add_code(code: str, code_type: str, is_primary: bool) -> None:
        normalized = normalize_code(code)
        if normalized in seen_normalized_codes:
            return

        seen_normalized_codes.add(normalized)
        codes.append((code, code_type, is_primary))

    if asset.inventory_number is not None:
        add_code(asset.inventory_number, "LELTARSZAM", True)

    add_code(asset.asset_number, "ESZKOZSZAM", False)

    if serial_number_can_be_code(asset.serial_number):
        assert asset.serial_number is not None
        add_code(asset.serial_number, "GYARI_SZAM", False)

    return codes


def get_or_create_zone(session: Session, code: str) -> InventoryZone:
    zone = session.scalar(select(InventoryZone).where(InventoryZone.code == code))
    if zone is not None:
        return zone

    zone = InventoryZone(
        code=code,
        site_code=f"{code}0000000",
        name=ZONE_NAMES.get(code, f"Leltárkörzet {code}"),
    )
    session.add(zone)
    session.flush()
    return zone


def get_or_create_asset_type(
    session: Session,
    *,
    name: str,
    name_normalized: str,
) -> AssetType:
    asset_type = session.scalar(
        select(AssetType).where(AssetType.name_normalized == name_normalized)
    )
    if asset_type is not None:
        return asset_type

    asset_type = AssetType(name=name, name_normalized=name_normalized)
    session.add(asset_type)
    session.flush()
    return asset_type


def create_asset_codes(
    session: Session,
    *,
    asset: Asset,
    zone: InventoryZone,
    source_asset: SourceAsset,
) -> None:
    for code, code_type, is_primary in asset_codes_for(source_asset):
        code_normalized = normalize_code(code)
        existing = session.scalar(
            select(AssetCode).where(
                AssetCode.zone_id == zone.id,
                AssetCode.code_normalized == code_normalized,
            )
        )

        if existing is not None:
            # Ugyanazon körzetben egy kód csak egy eszközhöz tartozhat.
            # A korábbi importált rekord megmarad, a későbbi ütköző kód kimarad.
            continue

        session.add(
            AssetCode(
                id=uuid4(),
                asset_id=asset.id,
                zone_id=zone.id,
                code=code,
                code_normalized=code_normalized,
                code_type=code_type,
                is_primary=is_primary,
            )
        )


def import_file(session: Session, source: Path | IO[bytes], file_name: str) -> ImportReport:
    """Egy SAP-lista sorait betölti; a commit a hívóé.

    Hibás fájlformátumnál (nem XLSX, hiányzó oszlop) kivételt dob, mielőtt bármit írna.
    A hibás sorok nem állítják meg a betöltést, a jelentésbe kerülnek.
    """
    report = ImportReport()
    # Előre beolvasva: a fájl- és fejléchiba így még az ImportBatch létrehozása előtt jön.
    rows = list(read_asset_rows(source))

    batch = ImportBatch(
        id=uuid4(),
        file_name=file_name,
        source_system="SAP",
        imported_at=datetime.now(UTC),
    )
    session.add(batch)
    session.flush()

    for row_number, row in rows:
        report.rows_read += 1

        try:
            with session.begin_nested():
                source_asset = row_to_source_asset(row)

                existing_asset = session.scalar(
                    select(Asset.id).where(
                        Asset.asset_number == source_asset.asset_number,
                        Asset.sub_number == source_asset.sub_number,
                    )
                )
                if existing_asset is not None:
                    report.rows_skipped += 1
                    continue

                zone = get_or_create_zone(session, source_asset.zone_code)
                # A típus kategória, nem a megnevezés másolata; a javaslat kézzel felülírható.
                type_name = suggest_type(source_asset.name_normalized)
                asset_type = get_or_create_asset_type(
                    session,
                    name=type_name,
                    name_normalized=normalize_text(type_name),
                )

                asset = Asset(
                    id=uuid4(),
                    asset_number=source_asset.asset_number,
                    sub_number=source_asset.sub_number,
                    name=source_asset.name,
                    name_normalized=source_asset.name_normalized,
                    zone_id=zone.id,
                    asset_type_id=asset_type.id,
                    parent_asset_id=None,
                    original_asset=source_asset.original_asset,
                    tax_ref=source_asset.tax_ref,
                    activated_on=source_asset.activated_on,
                    gross_value=source_asset.gross_value,
                    accum_depreciation=source_asset.accum_depreciation,
                    book_value=source_asset.book_value,
                    currency=source_asset.currency,
                    serial_number=source_asset.serial_number,
                    quantity=source_asset.quantity,
                    import_batch_id=batch.id,
                )
                session.add(asset)
                session.flush()

                create_asset_codes(session, asset=asset, zone=zone, source_asset=source_asset)

            report.rows_ok += 1

        except (IntegrityError, TypeError, ValueError) as error:
            report.rows_failed += 1
            report.errors.append((row_number, str(error)))

    batch.rows_read = report.rows_read
    batch.rows_ok = report.rows_ok
    batch.rows_failed = report.rows_failed
    return report


def link_accessories(session: Session) -> int:
    """A tartozékokat a főeszközükhöz köti, és visszaadja a létrejött kapcsolatok számát.

    A forrásban az alszám hordozza a tartozékszerkezetet: a főeszköz alszáma 0, a
    tartozékoké 1-től folytatólagos, ugyanazon eszközszám alatt. A kapcsolatot csak az
    összes fájl beolvasása után lehet megállapítani, mert egy tartozék sora megelőzheti a
    főeszközéét, és a főeszköz a másik körzet állományában is lehet.
    """
    parent = aliased(Asset)
    parent_id = (
        select(parent.id)
        .where(parent.asset_number == Asset.asset_number, parent.sub_number == 0)
        .scalar_subquery()
    )

    session.execute(update(Asset).where(Asset.sub_number > 0).values(parent_asset_id=parent_id))

    linked = session.scalar(
        select(func.count())
        .select_from(Asset)
        .where(Asset.sub_number > 0, Asset.parent_asset_id.is_not(None))
    )
    return linked or 0
