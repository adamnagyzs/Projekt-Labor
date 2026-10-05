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

1. Klónozd a repót, és lépj a `codee` mappába:
   ```
   git clone https://github.com/adamnagyzs/Projekt-Labor.git
   cd Projekt-Labor/codee
   ```
2. Tedd a két forrásfájlt (`261 lista_20260909.XLSX`, `262 lista_20260909.XLSX`) a `codee/source-data` mappába. Ezek **nincsenek a repóban és nem is kerülhetnek bele**: az egyetem nem nyilvános adatai, és a metaadatukban személynév van. A csapat privát tárolójából vagy közvetlenül a csapattól kapod meg őket.
3. Indítsd el:
   ```
   uv run python scripts/start.py
   ```

Ez az egy parancs mindent elvégez: beállítások (`.env`, ha még nincs), Python és csomagok, adatbázis, séma, adatok betöltése (csak ha még üres), szerver és kliens. Első alkalommal kb. 1–2 perc, utána kb. 10 másodperc. A kliens bezárásával a szerver is leáll.

Belépés: szerver címe `http://127.0.0.1:8000`, az e-mail és a jelszó a `.env` `DEMO_USER_EMAIL` és `DEMO_USER_PASSWORD` sora.

A részletek, a kézi lépések és a hibaelhárítás: [codee/SETUP.md](codee/SETUP.md).
