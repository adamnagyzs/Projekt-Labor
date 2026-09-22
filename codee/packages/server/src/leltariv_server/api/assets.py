from fastapi import APIRouter, Depends, HTTPException, Query, status
from leltariv_contracts.assets import AssetListItem, AssetPage
from leltariv_domain.normalization import normalize_text
from leltariv_infrastructure.db.models import Asset, AssetCode, InventoryZone
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from leltariv_server.api.zones import require_current_user

router = APIRouter(prefix="/api/v1", tags=["assets"])


@router.get(
    "/assets",
    response_model=AssetPage,
    summary="Eszközök keresése és lapozott lekérdezése",
)
def list_assets(
    zone: str = Query(description="A körzet kódja, például: 261."),
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
    """Körzetre szűrt, név- és kódkeresést támogató eszközlista."""
    inventory_zone = session.scalar(select(InventoryZone).where(InventoryZone.code == zone))
    if inventory_zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott körzet nem található.",
        )

    filters = [Asset.zone_id == inventory_zone.id]

    if q:
        normalized_query = normalize_text(q)
        normalized_code = q.strip().upper()

        matching_asset_ids = select(AssetCode.asset_id).where(
            AssetCode.zone_id == inventory_zone.id,
            AssetCode.code_normalized.contains(normalized_code),
        )

        filters.append(
            or_(
                Asset.name_normalized.contains(normalized_query),
                Asset.id.in_(matching_asset_ids),
            )
        )

    base_query = select(Asset).where(*filters)
    total = session.scalar(select(func.count()).select_from(base_query.subquery())) or 0

    assets = session.scalars(
        base_query.order_by(Asset.asset_number, Asset.sub_number)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items: list[AssetListItem] = []
    for asset in assets:
        inventory_number = session.scalar(
            select(AssetCode.code).where(
                AssetCode.asset_id == asset.id,
                AssetCode.code_type == "LELTARSZAM",
                AssetCode.is_primary.is_(True),
            )
        )

        items.append(
            AssetListItem(
                id=asset.id,
                asset_number=asset.asset_number,
                sub_number=asset.sub_number,
                name=asset.name,
                zone_code=inventory_zone.code,
                inventory_number=inventory_number,
                quantity=asset.quantity,
                activated_on=asset.activated_on,
                serial_number=asset.serial_number,
            )
        )

    return AssetPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
