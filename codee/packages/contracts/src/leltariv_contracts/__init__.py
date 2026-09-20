"""Közös adatszerződések. A szerver ezzel validál, a kliens ugyanezzel parse-ol."""

from leltariv_contracts.assets import AssetCodeOut, AssetListItem, AssetPage, CodeType
from leltariv_contracts.auth import LoginRequest, LoginResponse, Role
from leltariv_contracts.zones import ZoneOut

__all__ = [
    "AssetCodeOut",
    "AssetListItem",
    "AssetPage",
    "CodeType",
    "LoginRequest",
    "LoginResponse",
    "Role",
    "ZoneOut",
]
