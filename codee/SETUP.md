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

## Ami még hiányzik: a compose

A hivatalos Supabase-fájl háromszáz sor healthcheckkel, volume-okkal és init-szkriptekkel.
Újragépelve elromlik, ezért másolni kell:

```bash
git clone --depth 1 https://github.com/supabase/supabase supabase-src
```

Ezután a `supabase-src/docker/` mappából ide kell a `docker-compose.yml`, a `volumes/` mappa és a
`.env.example` (ez utóbbit fésüld össze az itt lévővel).

A compose-ból töröld ezt a hat service-blokkot és minden rájuk mutató `depends_on` sort:
`rest`, `realtime`, `functions`, `analytics`, `vector`, `supavisor`.
Marad: `db`, `kong`, `meta`, `studio`, `auth`, `storage`, `imgproxy`.

A `volumes/api/kong.yml`-ben maradnak útvonalak a törölt PostgREST felé — ezek 502-t adnak, de
semmi mást nem rontanak el. Ha a `storage` vagy az `imgproxy` makacskodik, azok hagyhatók el
elsőként: a prototípusban még nincs eszközfotó.

## Portkiosztás

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
