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
Kell hozzá: Git, [uv](https://docs.astral.sh/uv/) és futó Rancher Desktop (dockerd motorral). Pythont nem kell külön telepíteni, az uv hozza. A részletes leírás, a hibaelhárítással együtt: [codee/SETUP.md](codee/SETUP.md).

Első alkalommal, a `codee` mappából:

1. `cd codee`
2. `cp .env.example .env` (beállítások; PowerShellben `copy .env.example .env`)
3. A két forrásfájl (`261 lista_20260909.XLSX`, `262 lista_20260909.XLSX`) a `codee/source-data` mappába; ezek nincsenek a repóban
4. `uv sync --frozen` (Python és függőségek, kb. 1 perc)
5. `docker compose up -d` (adatbázis indítása)
6. `uv run alembic upgrade head` (séma)
7. `uv run python scripts/seed.py` (adatok betöltése, kb. 30 mp; a végén: `Seed kész: 3620/3620 eszköz`)

Indítás minden alkalommal: `uv run python scripts/start.py` — elindítja az adatbázist, a szervert és a klienst; a kliens bezárásával minden leáll.

Belépés: szerver címe `http://127.0.0.1:8000`, az e-mail és a jelszó a `.env` `DEMO_USER_EMAIL` és `DEMO_USER_PASSWORD` sora.