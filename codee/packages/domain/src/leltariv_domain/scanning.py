"""A kódfeloldás és a darabszám szabálya: egy beolvasott kódból mi lesz a naplóban.

Az adatbázis nem hívódik innen. A szerver kikeresi, mely körzetekben szerepel a normalizált
kód, és a találatokat adja át. Mivel az `asset_code` táblán a `(zone_id, code_normalized)`
páros egyedi, egy körzetből legfeljebb egy találat jöhet, ezért a döntéshez nem kell
kódtípus-sorrend: elég tudni, van-e találat az aktív körzetben.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

ScanResult = Literal["FOUND", "UNKNOWN_CODE", "FOREIGN_ZONE", "SURPLUS"]


@dataclass(frozen=True)
class CodeMatch:
    asset_id: UUID
    zone_code: str


def resolve(matches: Sequence[CodeMatch], active_zone_code: str) -> tuple[ScanResult, UUID | None]:
    """A beolvasás eredménye és a hozzá tartozó eszköz. `SURPLUS`-t soha nem ad.

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


def count_result(expected: int, counted_before: int, quantity: int) -> ScanResult:
    """Saját körzetbeli találatnál: túllépi-e ez a beolvasás a nyilvántartott darabszámot.

    A többletet nem tároljuk, mindig a naplóból számoljuk. A `SURPLUS` csak azt rögzíti, hogy
    a beolvasás pillanatában már több darab került elő, mint amennyi nyilvántartásban van.
    """
    return "FOUND" if counted_before + quantity <= expected else "SURPLUS"


def scan_message(
    result: ScanResult,
    *,
    raw_code: str,
    asset_name: str | None,
    asset_zone_code: str | None,
    expected: int | None = None,
    counted: int | None = None,
) -> str:
    """A leltározónak szóló egy mondat. A kliens ezt jeleníti meg változatlanul."""
    if result == "SURPLUS":
        return (
            f"Többlet: {asset_name}. {counted} db a nyilvántartott {expected} helyett. "
            "Ha tévedés, vond vissza."
        )

    if result == "FOUND":
        if expected is None or counted is None or expected <= 1:
            return f"Rendben: {asset_name}."
        if counted < expected:
            return f"Rendben: {asset_name}. {counted}/{expected} db, hiányzik {expected - counted}."
        return f"Rendben: {asset_name}. Megvan mind a(z) {expected} db."

    if result == "FOREIGN_ZONE":
        if asset_name is None:
            return f"Idegen körzet: a(z) {raw_code} kód több másik körzetben is szerepel."
        return f"Idegen körzet: {asset_name} a(z) {asset_zone_code} körzetben van nyilvántartva."

    return f"Ismeretlen kód: {raw_code}. Rögzítettük, de nem tartozik hozzá eszköz."


def undo_message(raw_code: str, quantity: int) -> str:
    """A visszavonás visszajelzése; a `quantity` a visszavont beolvasás darabszáma."""
    return f"Visszavonva: {raw_code}, {quantity} db."
