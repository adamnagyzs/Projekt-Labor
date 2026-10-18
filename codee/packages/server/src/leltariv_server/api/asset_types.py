from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from leltariv_contracts.assets import AssetDetail, AssetTypeCreate, AssetTypeOut, AssetTypeSet
from leltariv_domain.normalization import normalize_text
from leltariv_infrastructure.db.models import Asset, AssetType
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leltariv_server.api.assets import asset_detail
from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["asset-types"])


@router.get(
    "/asset-types",
    response_model=list[AssetTypeOut],
    summary="Eszköztípusok lekérdezése név szerint",
)
def list_asset_types(
    _current_user: object = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> list[AssetTypeOut]:
    rows = session.scalars(select(AssetType).order_by(AssetType.name, AssetType.id)).all()

    return [AssetTypeOut(id=row.id, name=row.name) for row in rows]


@router.post(
    "/asset-types",
    response_model=AssetTypeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Új eszköztípus létrehozása",
)
def create_asset_type(
    payload: AssetTypeCreate,
    _current_user: object = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AssetTypeOut:
    name = payload.name.strip()
    name_normalized = normalize_text(name)

    if not name_normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Az eszköztípus neve nem lehet üres.",
        )

    asset_type = AssetType(
        name=name,
        name_normalized=name_normalized,
    )
    session.add(asset_type)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ilyen nevű típus már van.",
        ) from exc

    session.refresh(asset_type)

    return AssetTypeOut(id=asset_type.id, name=asset_type.name)


@router.put(
    "/assets/{asset_id}/type",
    response_model=AssetDetail,
    summary="Eszköz típusának módosítása",
)
def update_asset_type(
    asset_id: UUID,
    payload: AssetTypeSet,
    _current_user: object = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AssetDetail:
    asset = session.get(Asset, asset_id)

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott eszköz nem található.",
        )

    asset_type = session.get(AssetType, payload.asset_type_id)

    if asset_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott eszköztípus nem található.",
        )

    asset.asset_type_id = asset_type.id
    session.commit()

    return asset_detail(session, asset.id)
