"""Label codes, scan normalisation, and QR payloads."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services import items as item_service
from app.services import labels as label_service
from app.services.errors import Conflict


def test_qr_payload_contains_only_the_identifier(db: Session) -> None:
    item = item_service.create(db, name="Camera")
    payload = label_service.payload_for(item.id)

    assert payload == f"/l/{item.id}"
    # Nothing mutable may be encoded into a code.
    assert "Camera" not in payload


def test_intrinsic_label_resolves_to_its_item(db: Session) -> None:
    item = item_service.create(db, name="Camera")

    assert label_service.find_item(db, item.id) is not None
    assert label_service.find_item(db, item.id).id == item.id


@pytest.mark.parametrize(
    "scanned",
    [
        "ABC123",
        "/l/ABC123",
        "l/ABC123",
        "http://nas.local:8080/l/ABC123",
        "https://hub.example.com/l/ABC123?utm=x",
        "  /l/ABC123  ",
    ],
)
def test_scan_normalisation_accepts_bare_codes_paths_and_urls(scanned: str) -> None:
    assert label_service.normalise_scan(scanned) == "ABC123"


def test_manufacturer_barcode_can_be_linked(db: Session) -> None:
    item = item_service.create(db, name="Battery pack")
    label_service.create(db, item, code="4006381333931", label_type="manufacturer")

    found = label_service.find_item(db, "4006381333931")

    assert found is not None
    assert found.id == item.id


def test_a_code_cannot_be_claimed_by_two_items(db: Session) -> None:
    first = item_service.create(db, name="First")
    second = item_service.create(db, name="Second")
    label_service.create(db, first, code="SHARED", label_type="code128")

    with pytest.raises(Conflict, match="already assigned"):
        label_service.create(db, second, code="SHARED", label_type="code128")


def test_relinking_the_same_code_to_the_same_item_is_idempotent(db: Session) -> None:
    item = item_service.create(db, name="Thing")
    first = label_service.create(db, item, code="CODE-1", label_type="code128")
    again = label_service.create(db, item, code="CODE-1", label_type="code128")

    assert first.id == again.id


def test_the_intrinsic_label_cannot_be_removed(db: Session) -> None:
    item = item_service.create(db, name="Thing")

    with pytest.raises(Conflict, match="intrinsic"):
        label_service.delete(db, item.labels[0])


def test_unknown_codes_resolve_to_nothing(db: Session) -> None:
    assert label_service.find_item(db, "NOT-A-REAL-CODE") is None


def test_qr_renders_as_svg_and_png(db: Session) -> None:
    item = item_service.create(db, name="Thing")

    svg = label_service.qr_svg(item.id)
    png = label_service.qr_png(item.id)

    assert svg.startswith(b"<?xml") or svg.lstrip().startswith(b"<svg")
    assert png.startswith(b"\x89PNG")
