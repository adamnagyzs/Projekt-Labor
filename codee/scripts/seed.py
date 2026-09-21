from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

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
from leltariv_infrastructure.db.models import (
    AppUser,
    Asset,
    AssetCode,
    AssetType,
    ImportBatch,
    InventoryPeriod,
    InventoryZone,
)
from leltariv_infrastructure.db.session import SessionLocal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

SOURCE_FILES = (
    "261 lista_20260909.XLSX",
    "262 lista_20260909.XLSX",
)

ZONE_NAMES = {
    "261": "Leltárkörzet 261",
    "262": "Leltárkörzet 262",
}


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
        raise ValueError(
            f"Érvénytelen egész érték: {field_name}={value!r}"
        ) from error


def to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("A pénzügyi érték nem lehet logikai érték.")

    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"Érvénytelen pénzügyi érték: {value!r}") from error


def row_to_seed_asset(row: Mapping[str, object]) -> SeedAsset:
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
    return is_meaningful_serial_number(serial_number)


def asset_codes_for_seed(asset: SeedAsset) -> list[tuple[str, str, bool]]:
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


def get_or_create_period(session: Session) -> InventoryPeriod:
    period = session.scalar(
        select(InventoryPeriod).where(InventoryPeriod.state == "ACTIVE")
    )
    if period is not None:
        return period

    period = InventoryPeriod(
        name="2026. évi leltár",
        year=2026,
        opened_at=datetime.now(UTC),
        state="ACTIVE",
    )
    session.add(period)
    return period


def seed_users(session: Session) -> None:
    users = (
        ("Rendszergazda", "ADMIN"),
        ("Leltározó", "LELTAROZO"),
        ("Olvasó", "OLVASO"),
    )

    for display_name, role in users:
        existing = session.scalar(select(AppUser).where(AppUser.role == role))
        if existing is None:
            session.add(
                AppUser(
                    id=uuid4(),
                    display_name=display_name,
                    role=role,
                    is_active=True,
                )
            )


def create_asset_codes(
    session: Session,
    *,
    asset: Asset,
    zone: InventoryZone,
    seed_asset: SeedAsset,
) -> None:
    for code, code_type, is_primary in asset_codes_for_seed(seed_asset):
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


def seed_file(session: Session, path: Path) -> tuple[int, int, int]:
    rows_read = 0
    rows_ok = 0
    rows_failed = 0

    batch = ImportBatch(
        id=uuid4(),
        file_name=path.name,
        source_system="SAP",
        rows_read=0,
        rows_ok=0,
        rows_failed=0,
        imported_at=datetime.now(UTC),
    )
    session.add(batch)
    session.flush()

    for row in read_asset_rows(path):
        rows_read += 1

        try:
            seed_asset = row_to_seed_asset(row)
            zone = get_or_create_zone(session, seed_asset.zone_code)
            asset_type = get_or_create_asset_type(
                session,
                name=seed_asset.name,
                name_normalized=seed_asset.name_normalized,
            )

            existing_asset = session.scalar(
                select(Asset).where(
                    Asset.asset_number == seed_asset.asset_number,
                    Asset.sub_number == seed_asset.sub_number,
                )
            )
            if existing_asset is not None:
                raise ValueError(
                    "Duplikált eszköz-kulcs: "
                    f"{seed_asset.asset_number}/{seed_asset.sub_number}"
                )

            asset = Asset(
                id=uuid4(),
                asset_number=seed_asset.asset_number,
                sub_number=seed_asset.sub_number,
                name=seed_asset.name,
                name_normalized=seed_asset.name_normalized,
                zone_id=zone.id,
                asset_type_id=asset_type.id,
                parent_asset_id=None,
                original_asset=seed_asset.original_asset,
                tax_ref=seed_asset.tax_ref,
                activated_on=seed_asset.activated_on,
                gross_value=seed_asset.gross_value,
                accum_depreciation=seed_asset.accum_depreciation,
                book_value=seed_asset.book_value,
                currency=seed_asset.currency,
                serial_number=seed_asset.serial_number,
                quantity=seed_asset.quantity,
                import_batch_id=batch.id,
            )
            session.add(asset)
            session.flush()

            create_asset_codes(
                session,
                asset=asset,
                zone=zone,
                seed_asset=seed_asset,
            )
            rows_ok += 1
        except (IntegrityError, TypeError, ValueError):
            rows_failed += 1
            raise

    batch.rows_read = rows_read
    batch.rows_ok = rows_ok
    batch.rows_failed = rows_failed

    return rows_read, rows_ok, rows_failed

def source_paths(source_dir: Path) -> list[Path]:
    """A két kötelező XLSX forrásfájl ellenőrzött elérési útja."""
    paths: list[Path] = []

    for file_name in SOURCE_FILES:
        path = source_dir / file_name

        if not path.is_file():
            raise FileNotFoundError(f"Hiányzó forrásfájl: {path}")

        paths.append(path)

    return paths


def main() -> None:
    """A teljes fejlesztői seed futtatása."""
    source_dir = Path(
        "/Users/ederdaniel/Projekt-Labor/codee/source-data"
    )

    session = SessionLocal()

    try:
        get_or_create_period(session)
        seed_users(session)

        totals = [
            seed_file(session, path)
            for path in source_paths(source_dir)
        ]

        session.commit()

        rows_read = sum(total[0] for total in totals)
        rows_ok = sum(total[1] for total in totals)
        rows_failed = sum(total[2] for total in totals)

        print(
            "Seed kész: "
            f"{rows_ok}/{rows_read} eszköz, "
            f"{rows_failed} hibás sor."
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()