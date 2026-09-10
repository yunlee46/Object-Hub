"""JSON API for items, photos, labels, and scanning."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Item
from app.schemas import (
    ItemDetail,
    ItemIn,
    ItemPage,
    ItemPatch,
    LabelIn,
    LabelOut,
    MoveIn,
    PhotoOut,
    ScanIn,
    ScanOut,
)
from app.services import items as item_service
from app.services import labels as label_service
from app.services import photos as photo_service
from app.services import search as search_service
from app.services import tags as tag_service

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=ItemPage)
def list_items(
    db: Session = Depends(get_db),
    q: str = "",
    location_id: str | None = None,
    parent_id: str | None = None,
    tag: list[str] = Query(default=[]),
    containers_only: bool = False,
    unplaced_only: bool = False,
    include_contained: bool = True,
    include_archived: bool = False,
    archived_only: bool = False,
    sort: str = "recent",
    page: int = 1,
    per_page: int = 50,
) -> ItemPage:
    results = search_service.run(
        db,
        search_service.Query(
            text=q,
            location_id=location_id,
            parent_id=parent_id,
            tag_slugs=tag,
            containers_only=containers_only,
            unplaced_only=unplaced_only,
            include_contained=include_contained,
            include_archived=include_archived,
            archived_only=archived_only,
            sort=sort,
            page=page,
            per_page=per_page,
        ),
    )
    return ItemPage(
        items=results.items,
        total=results.total,
        page=results.page,
        per_page=results.per_page,
        pages=results.pages,
    )


@router.post("", response_model=ItemDetail, status_code=201)
def create_item(payload: ItemIn, db: Session = Depends(get_db)) -> Item:
    return item_service.create(
        db,
        name=payload.name,
        description=payload.description,
        notes=payload.notes,
        quantity=payload.quantity,
        can_contain_items=payload.can_contain_items,
        parent_id=payload.parent_id,
        location_id=payload.location_id,
        tags=payload.tags,
    )


@router.get("/{item_id}", response_model=ItemDetail)
def get_item(item_id: str, db: Session = Depends(get_db)) -> Item:
    return item_service.get(db, item_id)


@router.patch("/{item_id}", response_model=ItemDetail)
def update_item(item_id: str, payload: ItemPatch, db: Session = Depends(get_db)) -> Item:
    item = item_service.get(db, item_id)
    unset: set[str] = set()
    if payload.clear_parent:
        unset.add("parent_id")
    if payload.clear_location:
        unset.add("location_id")
    return item_service.update(
        db,
        item,
        name=payload.name,
        description=payload.description,
        notes=payload.notes,
        quantity=payload.quantity,
        can_contain_items=payload.can_contain_items,
        parent_id=payload.parent_id,
        location_id=payload.location_id,
        tags=tag_service.parse(payload.tags) if payload.tags is not None else None,
        move_note=payload.move_note,
        unset=unset,
    )


@router.post("/{item_id}/move", response_model=ItemDetail)
def move_item(item_id: str, payload: MoveIn, db: Session = Depends(get_db)) -> Item:
    item = item_service.get(db, item_id)
    return item_service.move(
        db,
        item,
        parent_id=payload.parent_id,
        location_id=payload.location_id,
        note=payload.note,
    )


@router.post("/{item_id}/archive", response_model=ItemDetail)
def archive_item(item_id: str, db: Session = Depends(get_db), cascade: bool = True) -> Item:
    item = item_service.get(db, item_id)
    item_service.archive(db, item, cascade=cascade)
    return item


@router.post("/{item_id}/restore", response_model=ItemDetail)
def restore_item(item_id: str, db: Session = Depends(get_db)) -> Item:
    return item_service.restore(db, item_service.get(db, item_id))


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, db: Session = Depends(get_db)) -> Response:
    item_service.delete(db, item_service.get(db, item_id))
    return Response(status_code=204)


@router.post("/{item_id}/photos", response_model=PhotoOut, status_code=201)
async def upload_photo(
    item_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PhotoOut:
    item = item_service.get(db, item_id)
    photo = photo_service.add(db, item, await file.read(), original_name=file.filename)
    return PhotoOut.model_validate(photo)


@router.post("/{item_id}/labels", response_model=LabelOut, status_code=201)
def add_label(item_id: str, payload: LabelIn, db: Session = Depends(get_db)) -> LabelOut:
    item = item_service.get(db, item_id)
    label = label_service.create(
        db, item, code=payload.code, label_type=payload.label_type, note=payload.note
    )
    return LabelOut.model_validate(label)


scan_router = APIRouter(tags=["scan"])


@scan_router.post("/scan", response_model=ScanOut)
def scan(payload: ScanIn, db: Session = Depends(get_db)) -> ScanOut:
    code = label_service.normalise_scan(payload.code)
    item = label_service.find_item(db, payload.code)
    return ScanOut(
        code=code,
        found=item is not None,
        item=item,
        url=f"/items/{item.id}" if item else None,
    )
