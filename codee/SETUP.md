# Telepítés és indítás

Egyetlen parancs viszi végig: friss gépen kb. 1–2 perc a kliensig (plusz a Docker-képek első
letöltése), utána minden indítás kb. 10 másodperc. Minden parancs a `codee` mappából fut. 2026.
október 5-én tiszta klónon, üres adatbázissal kipróbáltuk.

## 1. Ami kell hozzá (egyszer)

| Mi | Miért | Honnan |
|---|---|---|
| Git | a repó letöltéséhez | <https://git-scm.com> |
| uv | ez hozza a Python 3.12-t és minden csomagot, Pythont külön nem kell telepíteni | lent |
| Rancher Desktop | ebben fut a PostgreSQL | <https://rancherdesktop.io> |

Az uv telepítése (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

A Rancher Desktopban a **Preferences → Container Engine** legyen **dockerd (moby)**, különben a
`docker compose` parancs nem működik. Indításkor legyen bekapcsolva; az első indulása eltart egy
darabig, ezt érdemes előre megvárni.

## 2. Indítás egy paranccsal (első alkalommal is)

```bash
git clone https://github.com/adamnagyzs/Projekt-Labor.git
```

```bash
cd Projekt-Labor/codee
```

A két forrásfájlt (`261 lista_20260909.XLSX`, `262 lista_20260909.XLSX`, pontosan ezzel a névvel)
másold a `codee/source-data` mappába; ha nincs ilyen mappa, hozd létre. Ezek nincsenek a repóban,
mert a metaadatukban személyes adat van, és a `.gitignore` minden xlsx-et kizár. Ha máshol vannak,
a `.env`-ben a `SOURCE_XLSX_DIR` sorba írd a mappájukat.

```bash
uv run python scripts/start.py
```

Ennyi. A szkript sorban:

1. ha nincs `.env`, létrehozza a mintából (a meglévőt nem írja felül);
2. az `uv run` telepíti a Pythont és a csomagokat, ha még nincsenek meg;
3. elindítja a konténereket, és megvárja, hogy az adatbázis fogadjon (`docker compose up -d --wait`);
4. felépíti vagy frissíti a sémát (`alembic upgrade head`);
5. betölti az adatokat, **ha az adatbázis még üres** (kb. 30 mp; különben kiírja, hogy kihagyta);
6. elindítja a szervert, megvárja, hogy válaszoljon;
7. megnyitja a klienst. A kliens ablakának bezárásával a szerver is leáll.

Első alkalommal ezt kell látnod:

```text
Adatbázis indítása...
Adatbázis-séma...
Adatok...
Seed kész: 3620/3620 eszköz, 0 hibás sor, 763 tartozék a főeszközéhez kötve.
Szerver indítása...
Várom a szervert... kész.
Kliens indítása. Az ablak bezárásával minden leáll.
```

Ugyanezt csinálja a `Leltariv.exe`, ami dupla kattintással indul; ez nincs a repóban, de egy
paranccsal elkészül a `dist` mappába:

```bash
uv run --with pyinstaller pyinstaller --onefile --name Leltariv scripts/start.py
```

A bejelentkező ablakba:

| Mező | Érték |
|---|---|
| Szerver címe | `http://127.0.0.1:8000` (nem `localhost`, lásd a 6. pontot) |
| E-mail | a `.env` `DEMO_USER_EMAIL` sora, alapból `admin@leltariv.local` |
| Jelszó | a `.env` `DEMO_USER_PASSWORD` sora |

Elgépelt jelszó után az ablak visszajön, újra lehet próbálni. A kliens megjegyzi a címet és az
e-mailt, a jelszót nem.

## 3. Kézzel, lépésenként

Csak akkor kell, ha egy lépést külön akarsz futtatni (például hibakereséskor). Ugyanaz, mint amit a
szkript csinál. A `.env`-et csak akkor másold, ha még nincs: a meglévőt felülírná.

```bash
uv sync --frozen
```

```bash
docker compose up -d --wait
```

```bash
uv run alembic upgrade head
```

```bash
uv run python scripts/seed.py
```

Szerver és kliens, két külön ablakban:

```bash
uv run uvicorn leltariv_server.main:app --host 127.0.0.1 --port 8000
```

```bash
uv run python -m leltariv_client.app
```

## 4. Címek és portok

| Cím | Mi |
|---|---|
| <http://127.0.0.1:8000/docs> | a szerver Swagger-felülete, itt minden végpont kipróbálható |
| <http://127.0.0.1:8000/health> | `{"status":"ok","database":"ok"}`, ha a szerver és az adatbázis is él |
| <http://127.0.0.1:5050> | pgAdmin; az adatbázishoz a host `leltariv-db`, port `5432`, a jelszó a `.env` `POSTGRES_PASSWORD`-je |

A portok csak a saját gépről érhetők el (8000 szerver, 5432 PostgreSQL, 5050 pgAdmin).

## 5. Tiszta adatbázis (például bemutató előtt)

Törli a beolvasásokat és mindent, majd újratölt; kb. 30 másodperc.

```bash
uv run alembic downgrade base
```

```bash
uv run alembic upgrade head
```

```bash
uv run python scripts/seed.py
```

A CI-vel azonos ellenőrzések, commit előtt:

```bash
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest
```

## 6. Ha valami nem megy

| Amit látsz | Ok | Teendő |
|---|---|---|
| `docker`: nem található, vagy „cannot connect to the Docker API” | a Rancher Desktop nem fut, vagy containerd a motor | indítsd el; Preferences → Container Engine → dockerd (moby) |
| `Hiányzó forrásfájl: …` / „Az adatok betöltése nem sikerült” | nincs meg a két XLSX | 2. pont, a `source-data` mappa vagy a `SOURCE_XLSX_DIR` |
| „Az adatbázis már be van töltve …, a seed kihagyva.” | már van adat | ez a helyes; újratöltés: az 5. pont |
| a seed nem találja az XLSX-et, pedig korábban ment | a `.env`-et felülírta a minta (`cp .env.example .env`) | írd vissza a `SOURCE_XLSX_DIR`-t, vagy tedd a fájlokat a `source-data` mappába |
| a szerver első kérése, vagy a seed eleje percekig áll | a `.env` `DATABASE_URL`-jében `localhost` van | írd át `127.0.0.1`-re (Windowson a localhost előbb IPv6-on próbál) |
| a kliensben minden kérés kb. 2 másodperc | a bejelentkezésnél `localhost` a szerver címe | írd át `http://127.0.0.1:8000`-ra; megmarad |
| „Érvénytelen vagy lejárt token.” | a belépés 1 óráig érvényes | zárd be a klienst és lépj be újra |
| „A szerver nem válaszolt időben”, vagy a 8000-es port foglalt | egy korábbi szerver még fut | lent |
| a pgAdmin konténer újraindul körbe | `.local` végű `PGADMIN_EMAIL` | maradjon a mintabeli `admin@leltariv.hu` |
| az 5432-es port foglalt | fut egy helyi PostgreSQL | a `.env`-ben `POSTGRES_PORT` és a `DATABASE_URL` portja legyen ugyanaz a szabad port |

A 8000-es portot foglaló folyamat leállítása (PowerShell):

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## 7. Később: a Supabase-stack (a futtatáshoz nem kell)

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
DATABASE_URL=postgresql+psycopg://postgres:<supabase_postgres_password>@127.0.0.1:5432/postgres
AUTH_MODE=gotrue
GOTRUE_URL=http://localhost:8100/auth/v1
JWT_SECRET=<a supabase/.env-bol atmasolva>
```

A séma és a seed változatlan marad, mert mindkét fázisban ugyanaz a PostgreSQL.

> A `supabase/.env` **valódi titkokat tartalmaz** a generálás után. A gyökér `.gitignore` minden
> `.env`-et kizár, de érdemes ellenőrizni, hogy tényleg nem jelenik-e meg a `git status`-ban.

### Portkiosztás a 2. fázisban

A Supabase gyárilag a **8000-es portra teszi a Kongot**, ami ütközne a FastAPI-val. Ezért a
`.env`-ben `KONG_HTTP_PORT=8100`.

| Port | Mi |
|---|---|
| 8000 | FastAPI |
| 8100 | Kong (Supabase átjáró) |
| 3000 | Supabase Studio |
| 5432 | PostgreSQL |

Ellenőrizni kell, hogy nem fut-e valakinek helyi Postgresa az 5432-n.
