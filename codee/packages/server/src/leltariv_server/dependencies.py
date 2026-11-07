"""A végpontok közös FastAPI-függőségei.

Azért külön modul, mert a hitelesítés minden router számára kell. Ha az egyik
erőforrás-router tartja, a többinek onnan kellene importálnia, és az olyan csatolást
hozna létre az eszközlista és a körzetek között, aminek semmi köze a tartalmukhoz.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from leltariv_infrastructure.db.models import AppUser
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy.orm import Session

from leltariv_server.services.auth import get_current_user


def require_current_user(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AppUser:
    """A kérés Bearer tokenjéhez tartozó aktív felhasználó, vagy 401."""
    return get_current_user(authorization, session)


def require_admin(user: AppUser = Depends(require_current_user)) -> AppUser:  # noqa: B008
    """Csak rendszergazda: az import és a visszatöltés az egész adatbázist érinti."""
    if user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ehhez rendszergazdai jogosultság kell.",
        )
    return user
