"""Labels and code resolution.

A label holds an opaque, permanent code. QR payloads contain only a resolver path
plus the item identifier, so nothing mutable is ever printed into a code.
"""

from __future__ import annotations

import io

import qrcode
import qrcode.image.svg
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item, Label
from app.services.errors import Conflict, NotFound, ValidationError

RESOLVER_PREFIX = "/l/"


def payload_for(code: str) -> str:
    """The exact string encoded into a QR code.

    Relative by design: the same sticker works whether the stack is reached over a
    LAN hostname, a Tailscale address, or a reverse proxy.
    """
    return f"{RESOLVER_PREFIX}{code}"


def normalise_scan(raw: str) -> str:
    """Reduce a scanned string to a bare code.

    Accepts the bare code, the resolver path, or a full URL wrapping either.
    """
    value = (raw or "").strip()
    if not value:
        raise ValidationError("Nothing was scanned.")
    if "://" in value:
        value = value.split("://", 1)[1]
        value = value[value.find("/") :] if "/" in value else ""
    value = value.split("?", 1)[0].split("#", 1)[0]
    marker = value.find(RESOLVER_PREFIX)
    if marker != -1:
        value = value[marker + len(RESOLVER_PREFIX) :]
    value = value.strip("/").strip()
    # A scanner that drops the leading slash still yields "l/<code>".
    bare_prefix = RESOLVER_PREFIX.strip("/") + "/"
    if value.startswith(bare_prefix):
        value = value[len(bare_prefix) :]
    return value.strip("/").strip()


def create(
    db: Session,
    item: Item,
    *,
    code: str,
    label_type: str = Label.QR,
    note: str | None = None,
) -> Label:
    code = (code or "").strip()
    if not code:
        raise ValidationError("A label needs a code.")
    if len(code) > 200:
        raise ValidationError("Label codes are limited to 200 characters.")
    if label_type not in Label.TYPES:
        raise ValidationError(f"Unknown label type: {label_type}")

    existing = db.scalar(select(Label).where(Label.code == code))
    if existing is not None:
        if existing.item_id == item.id:
            return existing
        raise Conflict(f"That code is already assigned to {existing.item.name}.")

    label = Label(item_id=item.id, code=code, label_type=label_type, note=(note or None))
    db.add(label)
    db.flush()
    return label


def get(db: Session, label_id: str) -> Label:
    label = db.get(Label, label_id)
    if label is None:
        raise NotFound("That label does not exist.")
    return label


def delete(db: Session, label: Label) -> None:
    if label.code == label.item_id:
        raise Conflict("The intrinsic QR label cannot be removed; it is the item identifier.")
    db.delete(label)
    db.flush()


def find_item(db: Session, raw_code: str) -> Item | None:
    """Resolve a scanned string to an item, or None when the code is unknown."""
    code = normalise_scan(raw_code)
    if not code:
        return None
    label = db.scalar(select(Label).where(Label.code == code))
    if label is not None:
        return label.item
    # An item identifier always resolves, even if its label row was removed.
    return db.get(Item, code)


def qr_svg(code: str, *, box_size: int = 10, border: int = 2) -> bytes:
    """An SVG QR code, chosen so labels stay crisp at any print size."""
    image = qrcode.make(
        payload_for(code),
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=box_size,
        border=border,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue()


def qr_png(code: str, *, box_size: int = 10, border: int = 2) -> bytes:
    qr = qrcode.QRCode(
        box_size=box_size,
        border=border,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(payload_for(code))
    buffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return buffer.getvalue()
