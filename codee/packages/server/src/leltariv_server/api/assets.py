from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from leltariv_contracts.assets import (
    AssetCodeOut,
    AssetDetail,
    AssetListItem,
    AssetPage,
    CodeType,
)
from leltariv_domain.normalization import normalize_code, normalize_text
from leltariv_infrastructure.db.models import Asset, AssetCode, AssetType, InventoryZone
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["assets"])


def primary_inventory_numbers(
    session: Session,
    asset_ids: list[UUID],
) -> dict[UUID, str]:
    """Eszközönként visszaadja az elsődleges leltárszámot egy lekérdezéssel."""
    if not asset_ids:
        return {}

    code_rows = session.execute(
        select(AssetCode.asset_id, AssetCode.code).where(
            AssetCode.asset_id.in_(asset_ids),
            AssetCode.code_type == "LELTARSZAM",
            AssetCode.is_primary.is_(True),
        )
    ).all()

    primary_codes: dict[UUID, str] = {}
    for asset_id, code in code_rows:
        primary_codes.setdefault(asset_id, code)

    return primary_codes


def asset_list_item(
    asset: Asset,
    zone_code: str | None,
    primary_codes: dict[UUID, str],
) -> AssetListItem:
    """Adatbázis-eszközből a közös lista-szerződésnek megfelelő objektumot épít."""
    return AssetListItem(
        id=asset.id,
        asset_number=asset.asset_number,
        sub_number=asset.sub_number,
        name=asset.name,
        zone_code=zone_code or "",
        inventory_number=primary_codes.get(asset.id),
        quantity=asset.quantity,
        activated_on=asset.activated_on,
        serial_number=asset.serial_number,
    )


@router.get(
    "/assets",
    response_model=AssetPage,
    summary="Eszközök keresése és lapozott lekérdezése",
)
def list_assets(
    zone: str | None = Query(
        default=None,
        description="A körzet kódja, például: 261. Üresen hagyva mindegyik körzet.",
    ),
    q: str | None = Query(default=None, description="Szabad szöveges keresőkifejezés."),
    main_only: bool = Query(
        default=False,
        description="Csak főeszközök, vagyis alszám 0.",
    ),
    multi_only: bool = Query(
        default=False,
        description="Csak több darabos tételek.",
    ),
    page: int = Query(default=1, ge=1, description="Oldalszám, 1-től kezdve."),
    page_size: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Oldalméret, legfeljebb 100.",
    ),
    _current_user: object = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AssetPage:
    """Körzetre szűrt, név- és kódkeresést támogató eszközlista.

    A `zone` elhagyható: ilyenkor minden körzet eszközei jönnek. A kliens
    körzetválasztójában ez a „Mind" állás, és az az alapértelmezett, tehát ha ez
    kötelező paraméter lenne, a felület már induláskor hibát kapna.
    """
    filters: list[ColumnElement[bool]] = []
    zone_id: int | None = None

    if zone is not None:
        inventory_zone = session.scalar(select(InventoryZone).where(InventoryZone.code == zone))
        if inventory_zone is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="A megadott körzet nem található.",
            )
        zone_id = inventory_zone.id
        filters.append(Asset.zone_id == zone_id)

    if main_only:
        filters.append(Asset.sub_number == 0)

    if multi_only:
        filters.append(Asset.quantity > 1)
    if q:
        normalized_query = normalize_text(q)
        normalized_code = normalize_code(q)

        code_filters: list[ColumnElement[bool]] = [
            AssetCode.code_normalized.contains(normalized_code)
        ]
        if zone_id is not None:
            code_filters.append(AssetCode.zone_id == zone_id)

        matching_asset_ids = select(AssetCode.asset_id).where(*code_filters)

        filters.append(
            or_(
                Asset.name_normalized.contains(normalized_query),
                Asset.id.in_(matching_asset_ids),
            )
        )

    base_query = select(Asset).where(*filters)
    total = session.scalar(select(func.count()).select_from(base_query.subquery())) or 0

    # A körzetkód eszközönként jön, nem a szűrőből: ha a `zone` üres, egy lapon
    # több körzet eszközei is szerepelhetnek.
    rows = session.execute(
        select(Asset, InventoryZone.code)
        .join(InventoryZone, Asset.zone_id == InventoryZone.id, isouter=True)
        .where(*filters)
        .order_by(Asset.asset_number, Asset.sub_number)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # Az elsődleges leltárszámokat egyetlen lekérdezéssel szedjük össze a laphoz.
    # Eszközönként külön lekérdezve egy 50-es lap 51 kört jelentene az adatbázishoz.

    asset_ids = [asset.id for asset, _ in rows]
    primary_codes = primary_inventory_numbers(session, asset_ids)

    items = [
        asset_list_item(asset, asset_zone_code, primary_codes) for asset, asset_zone_code in rows
    ]

    return AssetPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/assets/{asset_id}",
    response_model=AssetDetail,
    summary="Egy eszköz részletes adatlapja",
)
def get_asset(
    asset_id: UUID,
    _current_user: object = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AssetDetail:
    row = session.execute(
        select(Asset, InventoryZone.code, AssetType.name)
        .join(InventoryZone, Asset.zone_id == InventoryZone.id)
        .join(AssetType, Asset.asset_type_id == AssetType.id, isouter=True)
        .where(Asset.id == asset_id)
    ).one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott eszköz nem található.",
        )

    asset, zone_code, asset_type_name = row

    code_rows = (
        session.execute(
            select(AssetCode)
            .where(AssetCode.asset_id == asset.id)
            .order_by(AssetCode.is_primary.desc(), AssetCode.code_type, AssetCode.code)
        )
        .scalars()
        .all()
    )

    codes = [
        AssetCodeOut(
            code=code.code,
            code_type=cast(CodeType, code.code_type),
            is_primary=code.is_primary,
        )
        for code in code_rows
    ]

    accessory_rows = session.execute(
        select(Asset, InventoryZone.code)
        .join(InventoryZone, Asset.zone_id == InventoryZone.id)
        .where(Asset.parent_asset_id == asset.id)
        .order_by(Asset.sub_number)
    ).all()

    accessory_ids = [accessory.id for accessory, _ in accessory_rows]
    accessory_primary_codes = primary_inventory_numbers(session, accessory_ids)

    accessories = [
        asset_list_item(accessory, accessory_zone_code, accessory_primary_codes)
        for accessory, accessory_zone_code in accessory_rows
    ]

    return AssetDetail(
        id=asset.id,
        asset_number=asset.asset_number,
        sub_number=asset.sub_number,
        name=asset.name,
        zone_code=zone_code,
        quantity=asset.quantity,
        activated_on=asset.activated_on,
        serial_number=asset.serial_number,
        asset_type=asset_type_name,
        codes=codes,
        accessories=accessories,
    )
