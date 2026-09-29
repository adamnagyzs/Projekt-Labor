"""Közös adatszerződések. A szerver ezzel validál, a kliens ugyanezzel parse-ol."""

from leltariv_contracts.assets import (
    AssetCodeOut,
    AssetDetail,
    AssetListItem,
    AssetPage,
    CodeType,
)
from leltariv_contracts.auth import LoginRequest, LoginResponse, Role
from leltariv_contracts.inventory import (
    ScanCreate,
    ScanOut,
    ScanResult,
    SessionCreate,
    SessionOut,
)
from leltariv_contracts.zones import ZoneOut

__all__ = [
    "AssetCodeOut",
    "AssetDetail",
    "AssetListItem",
    "AssetPage",
    "CodeType",
    "LoginRequest",
    "LoginResponse",
    "Role",
    "ScanCreate",
    "ScanOut",
    "ScanResult",
    "SessionCreate",
    "SessionOut",
    "ZoneOut",
]
