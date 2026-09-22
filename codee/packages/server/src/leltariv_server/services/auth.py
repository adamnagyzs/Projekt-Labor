from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, status
from leltariv_infrastructure.db.models import AppUser
from sqlalchemy import select
from sqlalchemy.orm import Session

load_dotenv()

JWT_ALGORITHM = "HS256"


def get_auth_mode() -> str:
    return os.environ.get("AUTH_MODE", "local")


def required_env(name: str) -> str:
    """Kötelező szerverbeállítás, érthető hibaüzenettel.

    Közvetlen `os.environ[...]` helyett: hiányzó kulcsnál az KeyError-t dobna, amiből a
    kliens egy nyers 500-at lát, és a hibakeresés a bemutató közepén kezdődik.
    """
    value = os.environ.get(name)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Hiányzó szerverbeállítás: {name}. "
                "Másold a .env.example fájlt .env néven, és töltsd ki."
            ),
        )
    return value


def get_current_user(
    authorization: str | None,
    session: Session,
) -> AppUser:
    """Bearer token validálása és az aktív alkalmazásfelhasználó lekérése."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hiányzó vagy hibás Bearer token.",
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = jwt.decode(  # type: ignore[reportUnknownMemberType]
            token,
            required_env("JWT_SECRET"),
            algorithms=[JWT_ALGORITHM],
        )
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Érvénytelen vagy lejárt token.",
        ) from error

    # A frissítő token ugyanazzal a titokkal készül, tehát önmagában érvényes aláírású.
    # Ha nem zárnánk ki, egy hosszú életű refresh tokennel is lehetne kéréseket küldeni.
    if payload.get("type") == "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Frissítő tokennel nem lehet kérést hitelesíteni.",
        )

    user = session.scalar(select(AppUser).where(AppUser.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inaktív vagy ismeretlen felhasználó.",
        )

    return user


def local_login(email: str, password: str, session: Session) -> tuple[str, str, AppUser]:
    """Lokális demólogin a .env-ben rögzített felhasználóval.

    Tudatosan ideiglenes megoldás, és a védésen így is kell elmondani. A jelszót itt
    nem az adatbázis tárolja hashelve, hanem a `.env` nyílt szövegként, mert az
    `app_user` táblának ebben a mérföldkőben még nincs e-mail és jelszóhash oszlopa.
    Egyetlen demófelhasználó van, és az ADMIN szerepkörű seed-felhasználóra képződik le.

    A következő mérföldkő két lépése: az `app_user` kiegészítése e-maillel és bcrypt
    jelszóhashsel (a `passlib` már a függőségek között van), majd átállás GoTrue-ra
    `AUTH_MODE=gotrue` mellett. A kliens felé egyik sem látszik: a `LoginResponse`
    formátuma mindhárom esetben ugyanaz.
    """
    if get_auth_mode() != "local":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A local hitelesítés nincs engedélyezve.",
        )

    demo_email = required_env("DEMO_USER_EMAIL")
    demo_password = required_env("DEMO_USER_PASSWORD")

    if email != demo_email or password != demo_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hibás e-mail-cím vagy jelszó.",
        )

    user = session.scalar(
        select(AppUser).where(
            AppUser.role == "ADMIN",
            AppUser.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A seed admin felhasználó nem található.",
        )

    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=1)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "iat": now,
        "exp": expires_at,
    }

    access_token = jwt.encode(  # type: ignore[reportUnknownMemberType]
        payload,
        required_env("JWT_SECRET"),
        algorithm=JWT_ALGORITHM,
    )
    refresh_token = jwt.encode(  # type: ignore[reportUnknownMemberType]
        {
            "sub": str(user.id),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=7),
        },
        required_env("JWT_SECRET"),
        algorithm=JWT_ALGORITHM,
    )

    return access_token, refresh_token, user
