"""A kódfeloldás szabálya: egy beolvasott kódból mi lesz a naplóban.

Az adatbázis nem hívódik innen. A szerver kikeresi, mely körzetekben szerepel a normalizált
kód, és a találatokat adja át. Mivel az `asset_code` táblán a `(zone_id, code_normalized)`
páros egyedi, egy körzetből legfeljebb egy találat jöhet, ezért a döntéshez nem kell
kódtípus-sorrend: elég tudni, van-e találat az aktív körzetben.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

ScanResult = Literal["FOUND", "UNKNOWN_CODE", "FOREIGN_ZONE"]


@dataclass(frozen=True)
class CodeMatch:
    asset_id: UUID
    zone_code: str


def resolve(matches: Sequence[CodeMatch], active_zone_code: str) -> tuple[ScanResult, UUID | None]:
    """A beolvasás eredménye és a hozzá tartozó eszköz.

    Az aktív körzet találata nyer, így a két körzetben is meglévő leltárszám (pl. 024540)
    mindig a saját körzetében oldódik fel. Idegen találatnál csak akkor kötjük eszközhöz a
    beolvasást, ha egyértelmű, melyikről van szó.
    """
    if not matches:
        return "UNKNOWN_CODE", None

    for match in matches:
        if match.zone_code == active_zone_code:
            return "FOUND", match.asset_id

    if len(matches) == 1:
        return "FOREIGN_ZONE", matches[0].asset_id

    return "FOREIGN_ZONE", None


def scan_message(
    result: ScanResult,
    *,
    raw_code: str,
    asset_name: str | None,
    asset_zone_code: str | None,
) -> str:
    """A leltározónak szóló egy mondat. A kliens ezt jeleníti meg változatlanul."""
    if result == "FOUND":
        return f"Rendben: {asset_name}."

    if result == "FOREIGN_ZONE":
        if asset_name is None:
            return f"Idegen körzet: a(z) {raw_code} kód több másik körzetben is szerepel."
        return f"Idegen körzet: {asset_name} a(z) {asset_zone_code} körzetben van nyilvántartva."

    return f"Ismeretlen kód: {raw_code}. Rögzítettük, de nem tartozik hozzá eszköz."
