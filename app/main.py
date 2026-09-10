"""Application entrypoint.

The server-rendered UI and the JSON API are mounted on the same application and share
one service layer, so behaviour cannot drift between them.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import items as items_api
from app.api import locations as locations_api
from app.api import media as media_api
from app.config import get_settings
from app.services.errors import DomainError
from app.templating import STATIC_DIR, render
from app.web import routes as web_routes

logger = logging.getLogger("objecthub")

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Self-hosted tracking for real-world objects.",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(items_api.router, prefix="/api")
app.include_router(items_api.scan_router, prefix="/api")
app.include_router(locations_api.router, prefix="/api")
app.include_router(locations_api.tag_router, prefix="/api")
app.include_router(media_api.router, prefix="/api")
app.include_router(web_routes.router)


def _wants_json(request: Request) -> bool:
    if request.url.path.startswith("/api"):
        return True
    return "application/json" in request.headers.get("accept", "")


@app.exception_handler(DomainError)
def handle_domain_error(request: Request, exc: DomainError) -> Response:
    """Domain errors are user-facing: JSON for the API, a rendered page for the UI."""
    if _wants_json(request):
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
    return render(
        request,
        "error.html",
        {"status_code": exc.status_code, "message": exc.message},
        status_code=exc.status_code,
    )


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}
