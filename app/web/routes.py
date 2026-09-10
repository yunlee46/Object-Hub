"""Server-rendered UI routes.

Every handler delegates to the same service layer the JSON API uses. Forms post and
redirect so a refresh never repeats a mutation.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Item, Label
from app.services import items as item_service
from app.services import labels as label_service
from app.services import locations as location_service
from app.services import photos as photo_service
from app.services import search as search_service
from app.services import tags as tag_service
from app.templating import redirect, render

router = APIRouter(include_in_schema=False)


def _checkbox(value: str | None) -> bool:
    return value is not None and value.lower() not in ("", "0", "false", "off")


# ---------------------------------------------------------------- dashboard


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return render(
        request,
        "dashboard.html",
        {
            "nav": "dashboard",
            "counts": item_service.counts(db),
            "recent_items": item_service.recent(db, limit=8),
            "movements": item_service.recent_movements(db, limit=8),
            "locations": location_service.tree(db),
            "location_counts": location_service.item_counts(db),
            "tags": tag_service.with_counts(db)[:12],
        },
    )


# ---------------------------------------------------------------- items


@router.get("/items")
def item_list(
    request: Request,
    db: Session = Depends(get_db),
    q: str = "",
    location_id: str = "",
    parent_id: str = "",
    tag: list[str] = Query(default=[]),
    containers_only: str | None = None,
    unplaced_only: str | None = None,
    archived: str | None = None,
    sort: str = "recent",
    page: int = 1,
) -> HTMLResponse:
    settings = get_settings()
    query = search_service.Query(
        text=q,
        location_id=location_id or None,
        parent_id=parent_id or None,
        tag_slugs=[entry for entry in tag if entry],
        containers_only=_checkbox(containers_only),
        unplaced_only=_checkbox(unplaced_only),
        archived_only=_checkbox(archived),
        sort=sort if sort in search_service.SORTS else "recent",
        page=page,
        per_page=settings.items_per_page,
    )
    results = search_service.run(db, query)
    return render(
        request,
        "items/list.html",
        {
            "nav": "items",
            "query": query,
            "results": results,
            "locations": location_service.tree(db),
            "tags": tag_service.with_counts(db),
            "sorts": search_service.SORTS,
            "parent": db.get(Item, parent_id) if parent_id else None,
        },
    )


@router.get("/items/new")
def item_new(
    request: Request,
    db: Session = Depends(get_db),
    parent_id: str = "",
    location_id: str = "",
) -> HTMLResponse:
    return render(
        request,
        "items/form.html",
        {
            "nav": "items",
            "item": None,
            "containers": item_service.container_options(db),
            "locations": location_service.tree(db),
            "preset_parent_id": parent_id,
            "preset_location_id": location_id,
            "all_tags": [tag for tag, _ in tag_service.with_counts(db)][:20],
        },
    )


@router.post("/items")
async def item_create(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    notes: str = Form(""),
    quantity: int = Form(1),
    can_contain_items: str | None = Form(None),
    parent_id: str = Form(""),
    location_id: str = Form(""),
    tags: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
) -> Response:
    item = item_service.create(
        db,
        name=name,
        description=description,
        notes=notes,
        quantity=quantity,
        can_contain_items=_checkbox(can_contain_items),
        parent_id=parent_id or None,
        location_id=location_id or None,
        tags=tag_service.parse(tags),
    )
    added = await _store_uploads(db, item, photos)
    note = f" {added} photo(s) added." if added else ""
    return redirect(f"/items/{item.id}", f"Created {item.name}.{note}")


@router.get("/items/{item_id}")
def item_detail(request: Request, item_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    item = item_service.get(db, item_id)
    return render(
        request,
        "items/detail.html",
        {
            "nav": "items",
            "item": item,
            "containers": item_service.container_options(db, exclude_item_id=item.id),
            "locations": location_service.tree(db),
            "label_types": Label.TYPES,
        },
    )


@router.get("/items/{item_id}/edit")
def item_edit(request: Request, item_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    item = item_service.get(db, item_id)
    return render(
        request,
        "items/form.html",
        {
            "nav": "items",
            "item": item,
            "containers": item_service.container_options(db, exclude_item_id=item.id),
            "locations": location_service.tree(db),
            "preset_parent_id": item.parent_id or "",
            "preset_location_id": item.location_id or "",
            "all_tags": [tag for tag, _ in tag_service.with_counts(db)][:20],
        },
    )


@router.post("/items/{item_id}")
async def item_update(
    request: Request,
    item_id: str,
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    notes: str = Form(""),
    quantity: int = Form(1),
    can_contain_items: str | None = Form(None),
    parent_id: str = Form(""),
    location_id: str = Form(""),
    tags: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
) -> Response:
    item = item_service.get(db, item_id)
    item_service.update(
        db,
        item,
        name=name,
        description=description,
        notes=notes,
        quantity=quantity,
        can_contain_items=_checkbox(can_contain_items),
        parent_id=parent_id or None,
        location_id=location_id or None,
        tags=tag_service.parse(tags),
        unset={
            *(() if parent_id else ("parent_id",)),
            *(() if location_id else ("location_id",)),
            "description",
            "notes",
        },
    )
    await _store_uploads(db, item, photos)
    return redirect(f"/items/{item.id}", f"Saved {item.name}.")


@router.post("/items/{item_id}/move")
def item_move(
    item_id: str,
    db: Session = Depends(get_db),
    parent_id: str = Form(""),
    location_id: str = Form(""),
    note: str = Form(""),
) -> Response:
    item = item_service.get(db, item_id)
    item_service.move(
        db,
        item,
        parent_id=parent_id or None,
        location_id=location_id or None,
        note=note or None,
    )
    target = item.path_label
    if item.location is not None:
        target = f"{target} in {item.location.path_label}"
    return redirect(f"/items/{item.id}", f"Moved to {target}.")


@router.post("/items/{item_id}/archive")
def item_archive(item_id: str, db: Session = Depends(get_db)) -> Response:
    item = item_service.get(db, item_id)
    affected = item_service.archive(db, item)
    extra = f" and {len(affected) - 1} item(s) inside it" if len(affected) > 1 else ""
    return redirect(f"/items/{item.id}", f"Archived {item.name}{extra}.", "info")


@router.post("/items/{item_id}/restore")
def item_restore(item_id: str, db: Session = Depends(get_db)) -> Response:
    item = item_service.restore(db, item_service.get(db, item_id))
    return redirect(f"/items/{item.id}", f"Restored {item.name}.")


@router.post("/items/{item_id}/delete")
def item_delete(item_id: str, db: Session = Depends(get_db)) -> Response:
    item = item_service.get(db, item_id)
    name = item.name
    freed = len(item.children)
    item_service.delete(db, item)
    extra = f" {freed} item(s) it held are now unplaced." if freed else ""
    return redirect("/items", f"Deleted {name}.{extra}", "info")


async def _store_uploads(db: Session, item: Item, uploads: list[UploadFile]) -> int:
    added = 0
    for upload in uploads or []:
        if not upload or not upload.filename:
            continue
        data = await upload.read()
        if not data:
            continue
        photo_service.add(db, item, data, original_name=upload.filename)
        added += 1
    return added


@router.post("/items/{item_id}/photos")
async def item_photos(
    item_id: str,
    db: Session = Depends(get_db),
    photos: list[UploadFile] = File(default=[]),
) -> Response:
    item = item_service.get(db, item_id)
    added = await _store_uploads(db, item, photos)
    if not added:
        return redirect(f"/items/{item.id}", "No photos were selected.", "info")
    return redirect(f"/items/{item.id}", f"Added {added} photo(s).")


@router.post("/photos/{photo_id}/primary")
def photo_primary(photo_id: str, db: Session = Depends(get_db)) -> Response:
    photo = photo_service.set_primary(db, photo_service.get(db, photo_id))
    return redirect(f"/items/{photo.item_id}", "Primary photo updated.")


@router.post("/photos/{photo_id}/delete")
def photo_delete(photo_id: str, db: Session = Depends(get_db)) -> Response:
    photo = photo_service.get(db, photo_id)
    item_id = photo.item_id
    photo_service.delete(db, photo)
    return redirect(f"/items/{item_id}", "Photo deleted.", "info")


# ---------------------------------------------------------------- labels


@router.post("/items/{item_id}/labels")
def label_add(
    item_id: str,
    db: Session = Depends(get_db),
    code: str = Form(...),
    label_type: str = Form("manufacturer"),
    note: str = Form(""),
) -> Response:
    item = item_service.get(db, item_id)
    label_service.create(
        db, item, code=code.strip(), label_type=label_type, note=note or None
    )
    return redirect(f"/items/{item.id}", f"Linked code {code.strip()}.")


@router.post("/labels/{label_id}/delete")
def label_delete(label_id: str, db: Session = Depends(get_db)) -> Response:
    label = label_service.get(db, label_id)
    item_id = label.item_id
    label_service.delete(db, label)
    return redirect(f"/items/{item_id}", "Label removed.", "info")


@router.get("/labels/print")
def label_print(
    request: Request,
    db: Session = Depends(get_db),
    id: list[str] = Query(default=[]),
    location_id: str = "",
    containers_only: str | None = None,
) -> HTMLResponse:
    """A printable sheet. Either an explicit selection, or everything in a location."""
    if id:
        rows = list(db.scalars(select(Item).where(Item.id.in_(id))).unique())
        rows.sort(key=lambda row: row.name.lower())
    else:
        query = search_service.Query(
            location_id=location_id or None,
            containers_only=_checkbox(containers_only),
            sort="name",
            per_page=200,
        )
        rows = search_service.run(db, query).items
    return render(
        request,
        "labels/print.html",
        {
            "nav": "labels",
            "items": rows,
            "locations": location_service.tree(db),
            "selected_location_id": location_id,
            "containers_only": _checkbox(containers_only),
        },
    )


# ---------------------------------------------------------------- scanning


@router.get("/scan")
def scan_page(request: Request, code: str = "", db: Session = Depends(get_db)) -> HTMLResponse:
    unknown_code = ""
    if code:
        item = label_service.find_item(db, code)
        if item is not None:
            return RedirectResponse(f"/items/{item.id}", status_code=303)
        unknown_code = label_service.normalise_scan(code)
    return render(
        request,
        "scan.html",
        {
            "nav": "scan",
            "unknown_code": unknown_code,
            "containers": item_service.container_options(db) if unknown_code else [],
            "recent_items": item_service.recent(db, limit=6) if unknown_code else [],
        },
    )


@router.post("/scan")
def scan_submit(code: str = Form(...), db: Session = Depends(get_db)) -> Response:
    item = label_service.find_item(db, code)
    if item is None:
        normalised = label_service.normalise_scan(code)
        return redirect(
            f"/scan?code={quote(normalised, safe='')}",
            f"No item is linked to {normalised}.",
            "warning",
        )
    return RedirectResponse(f"/items/{item.id}", status_code=303)


@router.get("/l/{code}")
def resolve_label(code: str, db: Session = Depends(get_db)) -> Response:
    """The target of every printed QR code. Kept short so payloads stay small."""
    item = label_service.find_item(db, code)
    if item is None:
        return redirect(
            f"/scan?code={quote(label_service.normalise_scan(code), safe='')}",
            f"No item is linked to {code}.",
            "warning",
        )
    return RedirectResponse(f"/items/{item.id}", status_code=303)


# ---------------------------------------------------------------- locations


@router.get("/locations")
def location_list(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return render(
        request,
        "locations/list.html",
        {
            "nav": "locations",
            "locations": location_service.tree(db),
            "location_counts": location_service.item_counts(db),
        },
    )


@router.post("/locations")
def location_create(
    db: Session = Depends(get_db),
    name: str = Form(...),
    parent_id: str = Form(""),
    notes: str = Form(""),
) -> Response:
    location = location_service.create(
        db, name=name, parent_id=parent_id or None, notes=notes
    )
    return redirect("/locations", f"Added location {location.path_label}.")


@router.post("/locations/{location_id}")
def location_update(
    location_id: str,
    db: Session = Depends(get_db),
    name: str = Form(...),
    parent_id: str = Form(""),
    notes: str = Form(""),
) -> Response:
    location = location_service.get(db, location_id)
    location_service.update(
        db,
        location,
        name=name,
        parent_id=parent_id or None,
        notes=notes,
        unset={"notes", *(() if parent_id else ("parent_id",))},
    )
    return redirect("/locations", f"Saved {location.name}.")


@router.post("/locations/{location_id}/delete")
def location_delete(location_id: str, db: Session = Depends(get_db)) -> Response:
    location = location_service.get(db, location_id)
    name = location.name
    detached = len(location.items)
    location_service.delete(db, location)
    extra = f" {detached} item(s) are now without a location." if detached else ""
    return redirect("/locations", f"Deleted {name}.{extra}", "info")


# ---------------------------------------------------------------- tags


@router.get("/tags")
def tag_list(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return render(
        request,
        "tags/list.html",
        {"nav": "tags", "tags": tag_service.with_counts(db)},
    )


@router.post("/tags/{tag_id}")
def tag_update(
    tag_id: str,
    db: Session = Depends(get_db),
    name: str = Form(...),
    color: str = Form(""),
) -> Response:
    tag = tag_service.rename(db, tag_service.get(db, tag_id), name)
    if color:
        tag.color = color
    return redirect("/tags", f"Saved {tag.name}.")


@router.post("/tags/{tag_id}/delete")
def tag_delete(tag_id: str, db: Session = Depends(get_db)) -> Response:
    tag = tag_service.get(db, tag_id)
    name = tag.name
    tag_service.delete(db, tag)
    return redirect("/tags", f"Deleted tag {name}.", "info")


# ---------------------------------------------------------------- fallbacks


@router.get("/favicon.ico")
def favicon() -> Response:
    return RedirectResponse("/static/icon.svg", status_code=307)
