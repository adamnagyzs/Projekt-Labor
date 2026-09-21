# Projekt-Labor

Egyetemi eszközleltározó kliens–szerver rendszer. A leltározó a terepen vonalkódot olvas be egy asztali alkalmazásban, a rendszer pedig a beolvasásokat egy bővítés-alapú naplóba rögzíti, és ebből számolja ki a leltári eltéréseket.

## Csapat
* **Dani:** Szerver, Adatbázis
* **Ádám:** Kliens (PySide6), CI, Repository
* **Sanyi:** Projektvezetés, Architektúra, Kliens-szerver szerződések

## Technológiai Stack
* **Backend:** Python 3.12, FastAPI, Pydantic v2, PostgreSQL (Supabase)
* **Frontend:** Python 3.12, PySide6 (Qt 6)
* **Eszközök:** uv, ruff, pyright, pytest, Docker

## Futtatási útmutató
A projekt helyi futtatásához az alábbi lépések szükségesek:

1. `docker compose up -d` (adatbázis indítása)
2. `uv sync` (függőségek telepítése)
3. `alembic upgrade head` (adatbázis migrációk futtatása)
4. `uv run python seed.py` (tesztadatok betöltése)
5. `uv run uvicorn szerver_app:app --reload` (szerver indítása)
6. Kliens indítása: `uv run python -m leltariv_client.app`