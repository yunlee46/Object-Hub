"""Photo storage on a local volume.

Files are named by a generated identifier and validated by decoding the image, so an
upload is never trusted on its declared content type or its filename.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Item, Photo
from app.services.errors import NotFound, ValidationError
from app.services.ids import new_id

# Formats Pillow can decode that browsers can also display.
ALLOWED = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
    "GIF": ("gif", "image/gif"),
}

# Orientation-corrected on save, so a phone upload is never displayed sideways.
MAX_DIMENSION = 2560


def _paths(filename: str) -> tuple[Path, Path]:
    settings = get_settings()
    return settings.photos_dir / filename, settings.thumbnails_dir / filename


def add(db: Session, item: Item, data: bytes, original_name: str | None = None) -> Photo:
    settings = get_settings()
    if not data:
        raise ValidationError("That file was empty.")
    if len(data) > settings.max_upload_bytes:
        limit = settings.max_upload_bytes // (1024 * 1024)
        raise ValidationError(f"Photos are limited to {limit} MB.")

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        source = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("That file could not be read as an image.") from exc

    if source.format not in ALLOWED:
        supported = ", ".join(sorted(ALLOWED))
        raise ValidationError(f"Unsupported image format. Supported: {supported}.")

    extension, content_type = ALLOWED[source.format]
    filename = f"{new_id()}.{extension}"
    full_path, thumb_path = _paths(filename)

    image = ImageOps.exif_transpose(source) or source
    if image.mode in ("P", "LA", "RGBA") and extension in ("jpg",):
        image = image.convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
    image.save(full_path)

    thumbnail = image.copy()
    thumbnail.thumbnail((settings.thumbnail_size, settings.thumbnail_size), Image.LANCZOS)
    thumbnail.save(thumb_path)

    photo = Photo(
        item_id=item.id,
        filename=filename,
        original_name=(original_name or None),
        content_type=content_type,
        width=image.width,
        height=image.height,
        size_bytes=full_path.stat().st_size,
        is_primary=not item.photos,
    )
    db.add(photo)
    db.flush()
    source.close()
    return photo


def get(db: Session, photo_id: str) -> Photo:
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise NotFound("That photo does not exist.")
    return photo


def file_path(photo: Photo, *, thumbnail: bool = False) -> Path:
    full_path, thumb_path = _paths(photo.filename)
    if thumbnail and thumb_path.exists():
        return thumb_path
    if not full_path.exists():
        raise NotFound("That photo file is missing from storage.")
    return full_path


def set_primary(db: Session, photo: Photo) -> Photo:
    for sibling in photo.item.photos:
        sibling.is_primary = sibling.id == photo.id
    db.flush()
    return photo


def delete(db: Session, photo: Photo) -> None:
    was_primary = photo.is_primary
    item = photo.item
    for path in _paths(photo.filename):
        path.unlink(missing_ok=True)
    db.delete(photo)
    db.flush()
    if was_primary:
        remaining = [row for row in item.photos if row.id != photo.id]
        if remaining:
            remaining[0].is_primary = True
    db.flush()
