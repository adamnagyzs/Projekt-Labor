"""Egy eszköz története: felvétel, állapotváltások, felelősök, beolvasások, időrendben.

Semmi nem tárolódik külön a történethez. Minden sor egy olyan táblából jön, amelynek a
sorai nem törölhetők (az adatbázis triggerei őrzik), ezért a történet teljes.
"""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from leltariv_contracts.assets import STATUS_LABELS, HistoryEntry
from leltariv_infrastructure.db.models import (
    AppUser,
    Asset,
    AssetResponsible,
    AssetStatusChange,
    ImportBatch,
    InventoryPeriod,
    InventorySession,
    InventoryZone,
    Person,
    Room,
    Scan,
)
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from leltariv_server.api.rooms import room_label
from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["history"])


def status_text(old: str, new: str, reason: str) -> str:
    labels = cast(dict[str, str], STATUS_LABELS)
    return f"Állapot: {labels.get(old, old)} → {labels.get(new, new)}. Indoklás: {reason}"


def scan_text(result: str, quantity: int, zone_code: str, room: str | None) -> str:
    """Egy beolvasás vagy visszavonás egy mondatban."""
    where = f"a(z) {zone_code} körzetben" + (f", {room}" if room else "")
    if quantity < 0:
        return f"Beolvasás visszavonva: {-quantity} db ({where})."
    if result == "SURPLUS":
        return f"Többletként beolvasva {where}: {quantity} db."
    if result == "FOREIGN_ZONE":
        return f"Idegen körzetben beolvasva, {where}: {quantity} db."
    return f"Beolvasva {where}: {quantity} db."


def user_name(user: AppUser | None) -> str | None:
    return user.display_name if user is not None else None


@router.get(
    "/assets/{asset_id}/history",
    response_model=list[HistoryEntry],
    summary="Az eszköz története, a legfrissebb elöl",
)
def get_asset_history(
    asset_id: UUID,
    _current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> list[HistoryEntry]:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Az eszköz nem található.",
        )

    entries: list[HistoryEntry] = []

    if asset.created_at is not None:
        batch = session.get(ImportBatch, asset.import_batch_id) if asset.import_batch_id else None
        source = f" ({batch.file_name} importjával)" if batch and batch.file_name else ""
        entries.append(
            HistoryEntry(
                at=asset.created_at,
                kind="CREATED",
                text=f"Felvéve a nyilvántartásba{source}.",
            )
        )

    for change, user in session.execute(
        select(AssetStatusChange, AppUser)
        .join(AppUser, AssetStatusChange.changed_by == AppUser.id, isouter=True)
        .where(AssetStatusChange.asset_id == asset_id)
    ):
        entries.append(
            HistoryEntry(
                at=change.changed_at,
                kind="STATUS",
                text=status_text(change.old_status, change.new_status, change.reason),
                by=user_name(user),
            )
        )

    for link, person, user in session.execute(
        select(AssetResponsible, Person, AppUser)
        .join(Person, AssetResponsible.person_id == Person.id)
        .join(AppUser, AssetResponsible.assigned_by == AppUser.id, isouter=True)
        .where(AssetResponsible.asset_id == asset_id)
    ):
        until = f", {link.valid_to:%Y-%m-%d}-ig" if link.valid_to else ""
        entries.append(
            HistoryEntry(
                at=link.valid_from,
                kind="RESPONSIBLE",
                text=f"Felelős: {person.name}{until}.",
                by=user_name(user),
            )
        )

    for scan, zone_code, period_name, room, user in session.execute(
        select(Scan, InventoryZone.code, InventoryPeriod.name, Room, AppUser)
        .join(InventorySession, Scan.session_id == InventorySession.id)
        .join(InventoryZone, InventorySession.zone_id == InventoryZone.id)
        .join(InventoryPeriod, InventorySession.period_id == InventoryPeriod.id)
        .join(Room, Scan.room_id == Room.id, isouter=True)
        .join(AppUser, Scan.scanned_by == AppUser.id, isouter=True)
        .where(Scan.asset_id == asset_id)
    ):
        entries.append(
            HistoryEntry(
                at=scan.scanned_at,
                kind="UNDO" if scan.compensates_scan_id else "SCAN",
                text=scan_text(
                    scan.result,
                    scan.quantity_delta,
                    zone_code,
                    room_label(room) if room is not None else None,
                ),
                by=user_name(user),
                period=period_name,
            )
        )

    entries.sort(key=lambda entry: entry.at, reverse=True)
    return entries
