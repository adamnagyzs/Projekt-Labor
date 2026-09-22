from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from leltariv_contracts.assets import AssetListItem, AssetPage
from leltariv_domain.normalization import normalize_code, normalize_text
from leltariv_infrastructure.db.models import Asset, AssetCode, InventoryZone
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["assets"])


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
    primary_codes: dict[UUID, str] = {}
    if asset_ids:
        code_rows = session.execute(
            select(AssetCode.asset_id, AssetCode.code).where(
                AssetCode.asset_id.in_(asset_ids),
                AssetCode.code_type == "LELTARSZAM",
                AssetCode.is_primary.is_(True),
            )
        ).all()
        for asset_id, code in code_rows:
            primary_codes.setdefault(asset_id, code)

    items = [
        AssetListItem(
            id=asset.id,
            asset_number=asset.asset_number,
            sub_number=asset.sub_number,
            name=asset.name,
            zone_code=asset_zone_code or "",
            inventory_number=primary_codes.get(asset.id),
            quantity=asset.quantity,
            activated_on=asset.activated_on,
            serial_number=asset.serial_number,
        )
        for asset, asset_zone_code in rows
    ]

    return AssetPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
