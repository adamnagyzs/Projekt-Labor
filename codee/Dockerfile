# Leltárív szerver (FastAPI) konténerben.
#
# A compose `szerver` profilja építi és indítja:  docker compose --profile szerver up -d --build
# Induláskor lefuttatja a migrációt, utána indul a szerver; a seedet nem futtatja (az a
# két XLSX-et kéri, ami nincs a képben), az adatot a kliens Adminisztráció oldalán lehet
# importálni, vagy a gazdagépről a megszokott `uv run python scripts/seed.py`-jal.

FROM python:3.12-slim

# Az uv pontos verzióra pinelve, ugyanaz, amivel a uv.lock készült.
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Csak a szerver és a függőségei kerülnek be: a kliens (PySide6) és a fejlesztői eszközök nem.
COPY pyproject.toml uv.lock .python-version ./
COPY packages ./packages
RUN uv sync --frozen --no-dev --package leltariv-server

COPY alembic.ini ./
COPY migrations ./migrations

# Nem root felhasználó; a pillanatképek mappája az övé.
RUN useradd --create-home leltariv && mkdir -p /snapshots && chown leltariv /snapshots
USER leltariv

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn leltariv_server.main:app --host 0.0.0.0 --port 8000"]
