"""A leltár összehasonlításának szabályai: egy eszköz papíron és a naplóban.

Az adatbázis nem hívódik innen. A szerver összeszedi eszközönként a nyilvántartott
darabot, a naplóból számolt darabot és az állapotváltásokat, és ezek a függvények
döntenek. Így a szabály egy helyen van, és adatbázis nélkül tesztelhető.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# Ugyanezek a leltariv_contracts-ban; a tests/test_comparison.py ellenőrzi, hogy egyeznek.
AssetStatus = Literal["ACTIVE", "SCRAPPED", "LOST", "STOLEN", "OTHER"]
Category = Literal["FOUND", "PARTIAL", "MISSING", "SURPLUS"]
Verification = Literal["DIRECT", "INHERITED"]


@dataclass(frozen=True)
class StatusChange:
    changed_at: datetime
    old_status: AssetStatus
    new_status: AssetStatus


def status_at(
    current: AssetStatus, changes: Sequence[StatusChange], moment: datetime
) -> AssetStatus:
    """Az eszköz állapota egy korábbi időpontban, a változásnaplóból visszaszámolva.

    Az `asset.status` mindig a legutolsó váltás eredménye (az adatbázis trigger csak a
    naplón keresztül engedi módosítani), ezért a pillanat utáni első váltás `old_status`-a
    az akkori állapot. Ha a pillanat után nem volt váltás, a mostani érvényes.
    """
    later = [change for change in changes if change.changed_at > moment]
    if not later:
        return current
    return min(later, key=lambda change: change.changed_at).old_status


def expected_quantity(status: str, quantity: int) -> int:
    """A nyilvántartott darab, amit a leltár keres. Nem aktív eszközt nem várunk."""
    return quantity if status == "ACTIVE" else 0


def classify(
    expected: int, counted: int, parent_counted: int | None = None
) -> tuple[Category, Verification | None]:
    """Egy eszköz eredménye az időszakban.

    A tartozék (alszámos eszköz) gyakran nem kap külön címkét. Ha nincs saját beolvasása,
    de a főeszközét megtalálták, megtaláltnak tekintjük, és ezt `INHERITED` jelzi; így a
    hiánylistában csak az marad, amit valóban keresni kell.

    A nem aktív és be sem olvasott eszköz (`expected == counted == 0`) nem része az
    összehasonlításnak; ezt a hívó szűri ki.
    """
    if counted > expected:
        return "SURPLUS", "DIRECT"
    if counted > 0:
        return ("FOUND" if counted == expected else "PARTIAL"), "DIRECT"
    if parent_counted:
        return "FOUND", "INHERITED"
    return "MISSING", None


#: a lista sorrendje: amivel dolga van a leltározónak, az van elöl
CATEGORY_ORDER: dict[Category, int] = {"MISSING": 0, "PARTIAL": 1, "SURPLUS": 2, "FOUND": 3}


def progress_percent(expected_assets: int, missing: int) -> float:
    """A nyilvántartott eszközök hány százaléka került elő legalább részben."""
    if expected_assets == 0:
        return 100.0
    return round(100 * (expected_assets - missing) / expected_assets, 1)
