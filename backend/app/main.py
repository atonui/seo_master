from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.deployment import validate_production_settings
from app.api.auth import router as auth_router
from app.api.connections import router as connections_router
from app.api.settings import router as settings_router
from app.api.reports import router as reports_router
from app.api.chat import router as chat_router

app = FastAPI(title=settings.app_name, version="0.1.0")
validate_production_settings(settings)
app.include_router(auth_router)
app.include_router(connections_router)
app.include_router(settings_router)
app.include_router(reports_router)
app.include_router(chat_router)


@app.get("/api/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
