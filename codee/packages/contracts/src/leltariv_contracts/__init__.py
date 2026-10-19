"""Közös adatszerződések. A szerver ezzel validál, a kliens ugyanezzel parse-ol."""

from leltariv_contracts.assets import (
    AssetCodeOut,
    AssetDetail,
    AssetListItem,
    AssetPage,
    AssetTypeCreate,
    AssetTypeOut,
    AssetTypeSet,
    CodeType,
    PersonOut,
    ResponsibleSet,
)
from leltariv_contracts.auth import LoginRequest, LoginResponse, Role
from leltariv_contracts.inventory import (
    ScanCreate,
    ScanOut,
    ScanResult,
    SessionCreate,
    SessionOut,
)
from leltariv_contracts.rooms import RoomCreate, RoomOut
from leltariv_contracts.zones import ZoneOut

__all__ = [
    "AssetCodeOut",
    "AssetDetail",
    "AssetListItem",
    "AssetPage",
    "AssetTypeCreate",
    "AssetTypeOut",
    "AssetTypeSet",
    "CodeType",
    "LoginRequest",
    "LoginResponse",
    "PersonOut",
    "ResponsibleSet",
    "Role",
    "RoomCreate",
    "RoomOut",
    "ScanCreate",
    "ScanOut",
    "ScanResult",
    "SessionCreate",
    "SessionOut",
    "ZoneOut",
]
