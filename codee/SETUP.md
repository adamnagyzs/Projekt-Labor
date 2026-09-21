# A váz — mi van kész, és mi hiányzik még

Ez a mappa a Leltárív workspace-váza: a hat csomag, a közös adatszerződések, a lint- és
típusellenőrző-konfiguráció, és a tesztek. Erre épít Dani (adatbázis, szerver) és Ádám (kliens).

## Kész

```
codee/
├── pyproject.toml          uv workspace, ruff, pyright strict, pytest
├── .gitignore              a két XLSX és a .env ki van zárva
├── .env.example            a portkiosztással és a demó felhasználóval
├── packages/
│   ├── contracts/          a nyolc Pydantic modell — EZ A SZERZŐDÉS
│   ├── domain/             üres, külső függőség nélkül
│   ├── application/
│   ├── infrastructure/     Danié
│   ├── server/             Danié
│   └── client/             Ádámé
└── tests/test_contracts.py három teszt, hogy a CI-nak legyen mit futtatnia
```

## Az adatbázis — 1. fázis (ez van most)

`docker-compose.yml`: PostgreSQL 17 + pgAdmin. Külső fájl nem kell hozzá, azonnal indul.

```bash
docker compose up -d
```

Ezen fut a migráció, a seed és a szerver `AUTH_MODE=local` mellett. A séma a pgAdminban
megnézhető és megmutatható: `http://localhost:5050`, a belépés a `.env`-ben lévő
`PGADMIN_EMAIL` / `PGADMIN_PASSWORD` párral. A szerverhez a kapcsolat:
host `leltariv-db`, port `5432`.

| Port | Mi |
|---|---|
| 8000 | FastAPI |
| 5432 | PostgreSQL |
| 5050 | pgAdmin |

## Az adatbázis — 2. fázis: a Supabase-stack

A dolgozat 10.2 fejezete a Supabase-stacket írja le infrastruktúraként (db, kong, meta, studio,
auth, storage). A prototípus a sima Postgresen indult, mert az azonnal futott; a stack ráépül, a
séma és a seed változatlan marad. Az átállás annyi, hogy a `DATABASE_URL` a Supabase `db`
szolgáltatására mutat, és az `AUTH_MODE` `gotrue`-ra vált.

**Ez nem a bemutató előtti feladat.** A hivatalos telepítés kulcsgeneráló szkripteket futtat és
tíznél több konténert indít; erre akkor kerül sor, amikor van rá egy nyugodt délután.

A leírás: <https://supabase.com/docs/guides/self-hosting/docker>

### A telepítés

A `.sh` szkriptek miatt ezt **Git Bashban** futtasd, ne PowerShellben. A verziót érdemes tagre
fixálni, mert a `main` ágon a compose hetente változik:

```bash
git clone --depth 1 --branch self-hosted/v0.8.1 https://github.com/supabase/supabase supabase-src
```

```bash
mkdir -p supabase && cp -rf supabase-src/docker/. supabase/
```

```bash
cd supabase && cp .env.example .env
```

A titkokat **nem kézzel írjuk be**, hanem generáljuk — a leírás kifejezetten figyelmeztet, hogy a
`.env.example` alapértékeit soha ne hagyjuk bent:

```bash
sh utils/generate-keys.sh
```

```bash
sh utils/add-new-auth-keys.sh
```

Ez állítja elő a `JWT_SECRET`-et, a `SUPABASE_PUBLISHABLE_KEY`-t és a `SUPABASE_SECRET_KEY`-t,
valamint a többi kötelező kulcsot (`SECRET_KEY_BASE`, `VAULT_ENC_KEY` — pontosan 32 karakter,
`REALTIME_DB_ENC_KEY` — pontosan 16, `PG_META_CRYPTO_KEY`).

### Amit a `.env`-ben át kell állítani

A Supabase mindent a Kongon keresztül szolgál ki, és **gyárilag a 8000-es porton** — ott viszont a
FastAPI van. Ezért:

```
KONG_HTTP_PORT=8100
KONG_HTTPS_PORT=8143
SUPABASE_PUBLIC_URL=http://localhost:8100
API_EXTERNAL_URL=http://localhost:8100/auth/v1
SITE_URL=http://localhost:8100
DASHBOARD_USERNAME=leltariv
DASHBOARD_PASSWORD=...          # tartalmazzon legalább egy betűt, különben a Studio nem engedi be
POSTGRES_PASSWORD=...
```

### Indítás

```bash
docker compose pull
```

```bash
docker compose up -d --wait
```

A Studio ezután a `http://localhost:8100` címen van, basic authtal (a `DASHBOARD_*` párral). A
REST, az Auth és a Storage ugyanazon a porton, `/rest/v1/`, `/auth/v1/`, `/storage/v1/` alatt.

### Mit lehet kivenni

A leírás négy szolgáltatást nevez meg elhagyhatóként: **Realtime, Storage, imgproxy, Edge
Runtime**. Amíg nincs eszközfotó, a Storage és az imgproxy is mehet — ezzel jelentősen csökken a
memóriaigény.

**A PostgREST-et viszont hagyd bent.** A Studio tábla- és SQL-szerkesztője azon keresztül dolgozik,
tehát ha kiveszed, a Studio felét elveszíted. Ez nem mond ellent az architektúránknak: az állításunk
nem az, hogy a PostgREST nem létezik, hanem hogy **a kliens nem hívja** — a Kong és a PostgREST a
konténerhálózaton belül marad, a kliens gépéről nem érhető el. A dolgozat 10.3 fejezete pontosan ezt
írja; a 10.2 táblájában a `rest` sorát viszont „nem használjuk"-ról „csak a Studio használja
belülről"-re kell javítani.

### Átállás a mi alkalmazásunkban

Két sor a `codee/.env`-ben:

```
DATABASE_URL=postgresql+psycopg://postgres:<supabase_postgres_password>@localhost:5432/postgres
AUTH_MODE=gotrue
GOTRUE_URL=http://localhost:8100/auth/v1
JWT_SECRET=<a supabase/.env-bol atmasolva>
```

A séma és a seed változatlan marad, mert mindkét fázisban ugyanaz a PostgreSQL.

> A `supabase/.env` **valódi titkokat tartalmaz** a generálás után. A gyökér `.gitignore` minden
> `.env`-et kizár, de érdemes ellenőrizni, hogy tényleg nem jelenik-e meg a `git status`-ban.

## Portkiosztás a 2. fázisban

A Supabase gyárilag a **8000-es portra teszi a Kongot**, ami ütközne a FastAPI-val. Ezért a
`.env`-ben `KONG_HTTP_PORT=8100`.

| Port | Mi |
|---|---|
| 8000 | FastAPI |
| 8100 | Kong (Supabase átjáró) |
| 3000 | Supabase Studio |
| 5432 | PostgreSQL |

Ellenőrizni kell, hogy nem fut-e valakinek helyi Postgresa az 5432-n.

## Indítás

```bash
uv sync
```

```bash
uv run pytest
```

```bash
docker compose up -d
```

Ha a `uv sync` lefut, a három teszt zöld, és a Studio megnyílik a 3000-en, a váz kész.

## Munkarend

| Terület | Gazdája |
|---|---|
| `pyproject.toml`, `uv.lock`, `docker-compose.yml`, `.env.example`, `packages/contracts/` | Sanyi |
| `packages/infrastructure/`, `packages/server/`, `packages/domain/`, `scripts/seed.py` | Dani |
| `packages/client/`, `.github/`, `.gitignore`, `README.md` | Ádám |

Két ág a `main`-ről: `feat/db-server` és `feat/client`. Összefésülés hétfő 20:00.
**Új függőséget senki nem vesz fel egyedül** — szól, és egy helyen megy be, különben a `uv.lock`
ütközik.

A `qdarktheme` szándékosan nincs a kliens függőségei között: a legutóbbi kiadása Python 3.12 előtti,
és el tudja rontani a `uv sync`-et. Ádám adja hozzá, ha nála települ.

A részletes feladatlapokat és a háttéranyagot Sanyi küldi közvetlenül.
