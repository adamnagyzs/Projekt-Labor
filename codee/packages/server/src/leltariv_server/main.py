from fastapi import FastAPI

from leltariv_server.api.assets import router as assets_router
from leltariv_server.api.auth import router as auth_router
from leltariv_server.api.health import router as health_router
from leltariv_server.api.zones import router as zones_router

app = FastAPI(
    title="Leltárív API",
    version="0.1.0",
    description="Egyetemi eszközleltározó kliens–szerver rendszer API-ja.",
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(zones_router)
app.include_router(assets_router)
