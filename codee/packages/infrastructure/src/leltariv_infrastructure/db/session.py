import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

# Fejlesztoi alapertelmezes: pontosan az, amit a docker-compose.yml elindit.
# A .env felulirja, es a szerver eles inditasakor mindig onnan jon.
#
# Miert nem os.environ["DATABASE_URL"]: azt importalaskor olvasnank ki, tehat minden
# import adatbazis-konfiguraciot kovetelne. A CI-ban nincs .env, ezert a teszteket mar
# a begyujtesnel eldobta egy KeyError-ral. A create_engine egyebkent nem kapcsolodik,
# csak leirja, hova kellene - a kapcsolat az elso lekerdezesnel jon letre.
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:leltar2026@localhost:5432/leltariv"

DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI-függőség: kérésenként egy adatbázis session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
