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
Kell hozzá: Git, [uv](https://docs.astral.sh/uv/) és futó Rancher Desktop (dockerd motorral). Pythont nem kell külön telepíteni, az uv hozza.

1. `git clone https://github.com/adamnagyzs/Projekt-Labor.git`, majd `cd Projekt-Labor/codee`
2. A két forrásfájl (`261 lista_20260909.XLSX`, `262 lista_20260909.XLSX`) a `codee/source-data` mappába; ezek nincsenek a repóban
3. `uv run python scripts/start.py`

Ez az egy parancs mindent elvégez: beállítások (`.env`), Python és csomagok, adatbázis, séma, adatok betöltése (csak ha még üres), szerver és kliens. Első alkalommal kb. 1–2 perc, utána kb. 10 másodperc. A kliens bezárásával a szerver is leáll.

Belépés: szerver címe `http://127.0.0.1:8000`, az e-mail és a jelszó a `.env` `DEMO_USER_EMAIL` és `DEMO_USER_PASSWORD` sora.

A részletek, a kézi lépések és a hibaelhárítás: [codee/SETUP.md](codee/SETUP.md).
