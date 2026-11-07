from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from leltariv_domain.categories import DEFAULT_TYPES
from leltariv_domain.normalization import normalize_text
from leltariv_infrastructure.asset_import import (
    ZONE_NAMES,
    ImportReport,
    get_or_create_asset_type,
    get_or_create_zone,
    import_file,
    link_accessories,
)
from leltariv_infrastructure.db.models import (
    AppUser,
    Asset,
    AssetResponsible,
    AssetStatusChange,
    AssetType,
    InventoryPeriod,
    InventoryZone,
    Person,
    Room,
)
from leltariv_infrastructure.db.session import SessionLocal
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

SOURCE_FILES = (
    "261 lista_20260909.XLSX",
    "262 lista_20260909.XLSX",
)

DEMO_ROOMS: tuple[tuple[str, str, str], ...] = (
    ("261", "I-101", "Iroda"),
    ("261", "I-217", "Labor"),
    ("261", "I-220", "Raktár"),
    ("262", "G-012", "Műhely"),
    ("262", "G-105", "Tárgyaló"),
    ("262", "G-210", "Labor"),
)

#: Kitalált felelősök. Valódi munkatárs neve nem kerülhet ide: a 262-es forrásfájl
#: metaadatában van egy, azt sem használjuk.
DEMO_PERSONS: tuple[str, ...] = (
    "Teszt Anna",
    "Teszt Béla",
    "Teszt Csilla",
    "Teszt Dávid",
    "Teszt Erika",
)

#: ennyi 262-es főeszköz kap demófelelőst, eszközszám szerint, körbeforgóan
DEMO_RESPONSIBLE_COUNT = 40


def seed_demo_rooms(session: Session) -> int:
    """A hiányzó demóhelyiségeket létrehozza, a meglévőket nem módosítja."""
    created = 0

    for zone_code, room_number, name in DEMO_ROOMS:
        zone = get_or_create_zone(session, zone_code)
        existing = session.scalar(
            select(Room).where(
                Room.zone_id == zone.id,
                Room.room_number == room_number,
            )
        )
        if existing is not None:
            continue

        session.add(
            Room(
                id=uuid4(),
                zone_id=zone.id,
                room_number=room_number,
                name=name,
            )
        )
        session.flush()
        created += 1

    return created


def seed_demo_responsibles(session: Session) -> tuple[int, int]:
    """Kitalált felelősök és a hozzárendelésük; ami már megvan, azt nem hozza létre újra.

    A felületen beállított felelőst egy újabb seed nem írja felül.
    """
    zone = get_or_create_zone(session, "262")
    persons: list[Person] = []
    created = 0
    for name in DEMO_PERSONS:
        person = session.scalar(select(Person).where(Person.name == name))
        if person is None:
            person = Person(id=uuid4(), name=name, org_unit=ZONE_NAMES["262"])
            session.add(person)
            created += 1
        persons.append(person)
    session.flush()

    # Ha már van hozzárendelés (seedből vagy a felületről), egy újabb futás nem tesz hozzá többet.
    if session.scalar(select(func.count()).select_from(AssetResponsible)):
        return created, 0

    # Kézzelfogható eszközök kapjanak felelőst (bútor, gép, műszer), ne a licencek, amelyek az
    # eszközszám szerinti elejét adják a 262-nek, és az „Egyéb" típusba esnek.
    assets = session.scalars(
        select(Asset)
        .join(AssetType, Asset.asset_type_id == AssetType.id)
        .where(Asset.zone_id == zone.id, Asset.sub_number == 0, AssetType.name != "Egyéb")
        .order_by(Asset.asset_number)
        .limit(DEMO_RESPONSIBLE_COUNT)
    ).all()
    for index, asset in enumerate(assets):
        session.add(
            AssetResponsible(
                id=uuid4(),
                asset_id=asset.id,
                person_id=persons[index % len(persons)].id,
            )
        )
    session.flush()
    return created, len(assets)


def seed_demo_statuses(session: Session) -> int:
    """Üres állapotnaplónál a 262-es körzet utolsó három főeszközét jelöli meg."""
    # A napló ellenőrzése és feltöltése között egy másik tranzakció ne írhasson bele.
    session.execute(text("LOCK TABLE asset_status_change IN SHARE ROW EXCLUSIVE MODE"))
    if session.scalar(select(AssetStatusChange.id).limit(1)) is not None:
        return 0

    demo_statuses = (
        ("SCRAPPED", "Demó: selejtezési jegyzőkönyv 2026/1"),
        ("LOST", "Demó: a 2025-ös leltárban sem került elő"),
        ("STOLEN", "Demó: rendőrségi feljelentés"),
    )
    assets = session.scalars(
        select(Asset)
        .join(InventoryZone, Asset.zone_id == InventoryZone.id)
        .where(InventoryZone.code == "262", Asset.sub_number == 0)
        .order_by(Asset.asset_number.desc())
        .limit(len(demo_statuses))
    ).all()
    if len(assets) < len(demo_statuses):
        return 0

    for asset, (new_status, reason) in zip(assets, demo_statuses, strict=True):
        if not asset.name.startswith("Demó: "):
            asset.name = f"Demó: {asset.name}"
            asset.name_normalized = normalize_text(asset.name)
        session.add(
            AssetStatusChange(
                asset_id=asset.id,
                old_status="ACTIVE",
                new_status=new_status,
                reason=reason,
            )
        )
    session.flush()
    return len(assets)


def seed_default_types(session: Session) -> None:
    """Az üres kategória is választható legyen a felületen."""
    for name in DEFAULT_TYPES:
        get_or_create_asset_type(session, name=name, name_normalized=normalize_text(name))


def type_counts(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(
        select(AssetType.name, func.count(Asset.id))
        .join(Asset, Asset.asset_type_id == AssetType.id, isouter=True)
        .group_by(AssetType.name)
        .order_by(func.count(Asset.id).desc())
    ).all()
    return [(name, count) for name, count in rows]


def get_or_create_period(session: Session) -> InventoryPeriod:
    period = session.scalar(select(InventoryPeriod).where(InventoryPeriod.state == "ACTIVE"))
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


def get_source_dir() -> Path:
    """A forrásfájlok mappája.

    A `SOURCE_XLSX_DIR` környezeti változóból jön, mert a két XLSX nincs a repóban —
    személyes adat van a metaadatában —, tehát minden gépen máshol áll. Ha nincs
    beállítva, a repó `source-data` mappájába nézünk.
    """
    configured = os.environ.get("SOURCE_XLSX_DIR")

    if configured:
        return Path(configured)

    return Path(__file__).resolve().parent.parent / "source-data"


def source_paths(source_dir: Path) -> list[Path]:
    """A két kötelező XLSX forrásfájl ellenőrzött elérési útja."""
    paths: list[Path] = []

    for file_name in SOURCE_FILES:
        path = source_dir / file_name

        if not path.is_file():
            raise FileNotFoundError(
                f"Hiányzó forrásfájl: {path}\n"
                "Állítsd be a SOURCE_XLSX_DIR értékét a .env-ben arra a mappára, "
                "ahol a két XLSX van."
            )

        paths.append(path)

    return paths


def main() -> None:
    """A teljes fejlesztői seed futtatása."""
    source_dir = get_source_dir()
    session = SessionLocal()

    try:
        loaded = session.scalar(select(func.count()).select_from(Asset)) or 0

        if loaded:
            rooms_created = seed_demo_rooms(session)
            persons_created, assigned = seed_demo_responsibles(session)
            statuses_created = seed_demo_statuses(session)
            session.commit()

            print(f"Az adatbázis már be van töltve ({loaded} eszköz), az Excel-import kihagyva.")
            print(f"Új demóhelyiségek: {rooms_created}.")
            print(f"Új demófelelősök: {persons_created}, új hozzárendelés: {assigned}.")
            print(f"Új demóállapotok: {statuses_created}.")
            return

        get_or_create_period(session)
        seed_users(session)
        seed_default_types(session)

        reports: list[ImportReport] = []
        for path in source_paths(source_dir):
            report = import_file(session, path, path.name)
            reports.append(report)
            if report.errors:
                print(f"\n{path.name}: {len(report.errors)} hibás sor.")
                for row_number, message in report.errors[:20]:
                    print(f"Sor {row_number}: {message}")

        linked = link_accessories(session)
        rooms_created = seed_demo_rooms(session)
        persons_created, assigned = seed_demo_responsibles(session)
        statuses_created = seed_demo_statuses(session)

        session.commit()

        rows_read = sum(report.rows_read for report in reports)
        rows_ok = sum(report.rows_ok for report in reports)
        rows_failed = sum(report.rows_failed for report in reports)

        print(
            f"Seed kész: {rows_ok}/{rows_read} eszköz, {rows_failed} hibás sor, "
            f"{linked} tartozék a főeszközéhez kötve."
        )
        print(f"Új demóhelyiségek: {rooms_created}.")
        print(f"Új demófelelősök: {persons_created}, új hozzárendelés: {assigned}.")
        print(f"Új demóállapotok: {statuses_created}.")
        print("Típusonként:")
        for name, count in type_counts(session):
            print(f"  {name}: {count}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
