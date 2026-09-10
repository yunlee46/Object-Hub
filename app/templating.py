"""Jinja environment, flash messages, and shared template helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services import labels as label_service

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

FLASH_COOKIE = "oh_flash"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _relative_time(value: datetime | None) -> str:
    if value is None:
        return "never"
    moment = value if value.tzinfo else value.replace(tzinfo=UTC)
    seconds = int((datetime.now(UTC) - moment).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 45:
        return "just now"
    for limit, divisor, unit in (
        (3600, 60, "minute"),
        (86400, 3600, "hour"),
        (2592000, 86400, "day"),
        (31536000, 2592000, "month"),
    ):
        if seconds < limit:
            count = max(1, seconds // divisor)
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    years = max(1, seconds // 31536000)
    return f"{years} year{'s' if years != 1 else ''} ago"


def _absolute_time(value: datetime | None) -> str:
    if value is None:
        return ""
    moment = value if value.tzinfo else value.replace(tzinfo=UTC)
    return moment.strftime("%d %b %Y, %H:%M UTC")


def _query_with(request: Request, **overrides: Any) -> str:
    """Rebuild the current query string with some parameters replaced or dropped."""
    params: list[tuple[str, str]] = [
        (key, value) for key, value in request.query_params.multi_items()
        if key not in overrides
    ]
    for key, value in overrides.items():
        if value is None or value is False or value == "":
            continue
        if isinstance(value, list | tuple | set):
            params.extend((key, str(entry)) for entry in value)
        else:
            params.append((key, str(value)))
    encoded = urlencode(params)
    return f"?{encoded}" if encoded else ""


def _short_id(value: str, length: int = 8) -> str:
    return value[-length:] if value else ""


templates.env.filters["relative_time"] = _relative_time
templates.env.filters["absolute_time"] = _absolute_time
templates.env.filters["short_id"] = _short_id
templates.env.globals["query_with"] = _query_with
templates.env.globals["qr_payload"] = label_service.payload_for
templates.env.globals["app_name"] = get_settings().app_name


def flash(response: Any, message: str, kind: str = "success") -> Any:
    """Queue a one-shot message shown on the next rendered page.

    Stored in a plain short-lived cookie: it carries no privileges and is discarded
    as soon as it is read, so it needs no signing.
    """
    response.set_cookie(
        FLASH_COOKIE,
        json.dumps({"message": message, "kind": kind}),
        max_age=30,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


def _read_flash(request: Request) -> dict[str, str] | None:
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or "message" not in payload:
        return None
    return {"message": str(payload["message"])[:300], "kind": str(payload.get("kind", "success"))}


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    # The flash must be resolved before rendering, because Starlette renders the
    # template while constructing the response.
    pending = _read_flash(request)
    payload = {"request": request, "flash": pending, **(context or {})}
    response = templates.TemplateResponse(
        request=request, name=template, context=payload, status_code=status_code
    )
    if request.cookies.get(FLASH_COOKIE):
        response.delete_cookie(FLASH_COOKIE, path="/")
    return response


def redirect(url: str, message: str | None = None, kind: str = "success") -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    if message:
        flash(response, message, kind)
    return response
