"""Photo delivery and label rendering.

Photos are served by the application rather than a static mount so that a missing
file yields a clean 404 and so access can later be gated without moving routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import PhotoOut
from app.services import labels as label_service
from app.services import photos as photo_service

router = APIRouter(tags=["media"])

# Photo files are immutable once written, so they can be cached hard.
_IMMUTABLE = "public, max-age=31536000, immutable"


@router.get("/photos/{photo_id}")
def photo_file(photo_id: str, db: Session = Depends(get_db), thumb: bool = False) -> FileResponse:
    photo = photo_service.get(db, photo_id)
    return FileResponse(
        photo_service.file_path(photo, thumbnail=thumb),
        media_type=photo.content_type,
        headers={"Cache-Control": _IMMUTABLE},
    )


@router.post("/photos/{photo_id}/primary", response_model=PhotoOut)
def make_primary(photo_id: str, db: Session = Depends(get_db)) -> PhotoOut:
    photo = photo_service.set_primary(db, photo_service.get(db, photo_id))
    return PhotoOut.model_validate(photo)


@router.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: str, db: Session = Depends(get_db)) -> Response:
    photo_service.delete(db, photo_service.get(db, photo_id))
    return Response(status_code=204)


@router.delete("/labels/{label_id}", status_code=204)
def delete_label(label_id: str, db: Session = Depends(get_db)) -> Response:
    label_service.delete(db, label_service.get(db, label_id))
    return Response(status_code=204)


@router.get("/qr/{code}.svg")
def qr_svg(code: str, size: int = 10) -> Response:
    payload = label_service.qr_svg(code, box_size=max(2, min(size, 40)))
    return Response(
        payload, media_type="image/svg+xml", headers={"Cache-Control": _IMMUTABLE}
    )


@router.get("/qr/{code}.png")
def qr_png(code: str, size: int = 10) -> Response:
    payload = label_service.qr_png(code, box_size=max(2, min(size, 40)))
    return Response(payload, media_type="image/png", headers={"Cache-Control": _IMMUTABLE})
