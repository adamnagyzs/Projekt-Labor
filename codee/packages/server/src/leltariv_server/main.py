from fastapi import FastAPI

from leltariv_server.api.health import router as health_router

app = FastAPI(
    title="Leltárív API",
    version="0.1.0",
    description="Egyetemi eszközleltározó kliens–szerver rendszer API-ja.",
)

app.include_router(health_router)