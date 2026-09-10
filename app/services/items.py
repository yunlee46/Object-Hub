"""Item lifecycle: creation, editing, moving, archiving, and containment rules."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Item, Location, Movement
from app.services import labels as label_service
from app.services import tags as tag_service
from app.services.errors import Conflict, NotFound, ValidationError

MAX_DEPTH = 64


def get(db: Session, item_id: str) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise NotFound("That item does not exist.")
    return item


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _require_name(name: str | None) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("An item needs a name.")
    if len(name) > 200:
        raise ValidationError("Names are limited to 200 characters.")
    return name


def ancestor_ids(db: Session, item_id: str) -> set[str]:
    """Identifiers of every ancestor of an item, walking upwards defensively."""
    found: set[str] = set()
    current = db.get(Item, item_id)
    depth = 0
    while current is not None and current.parent_id and depth < MAX_DEPTH:
        if current.parent_id in found:
            break
        found.add(current.parent_id)
        current = db.get(Item, current.parent_id)
        depth += 1
    return found


def descendant_ids(db: Session, item_id: str) -> set[str]:
    """Identifiers of every descendant of an item, breadth first."""
    found: set[str] = set()
    frontier = [item_id]
    while frontier:
        rows = db.scalars(select(Item.id).where(Item.parent_id.in_(frontier))).all()
        fresh = [row for row in rows if row not in found]
        found.update(fresh)
        frontier = fresh
    return found


def _validate_parent(db: Session, item: Item | None, parent_id: str | None) -> None:
    """Check a proposed parent, raising when the move would be illegal."""
    if parent_id is None:
        return
    parent = db.get(Item, parent_id)
    if parent is None:
        raise ValidationError("The chosen container does not exist.")
    if not parent.can_contain_items:
        raise ValidationError(f"{parent.name} is not marked as able to contain items.")
    if item is not None:
        if parent.id == item.id:
            raise ValidationError("An item cannot contain itself.")
        if parent.id in descendant_ids(db, item.id):
            raise ValidationError(
                f"{parent.name} is already inside {item.name}, so that would create a loop."
            )


def _validate_location(db: Session, location_id: str | None) -> None:
    if location_id is None:
        return
    if db.get(Location, location_id) is None:
        raise ValidationError("The chosen location does not exist.")


def _location_label(db: Session, location_id: str | None) -> str | None:
    if location_id is None:
        return None
    location = db.get(Location, location_id)
    return location.path_label if location else None


def _item_label(db: Session, item_id: str | None) -> str | None:
    if item_id is None:
        return None
    item = db.get(Item, item_id)
    return item.name if item else None


def _record_movement(
    db: Session,
    item: Item,
    *,
    from_parent_id: str | None,
    from_location_id: str | None,
    note: str | None = None,
) -> Movement | None:
    """Append a movement row when the parent or location actually changed."""
    parent_changed = from_parent_id != item.parent_id
    location_changed = from_location_id != item.location_id
    if not (parent_changed or location_changed):
        return None

    from_parts = [
        part
        for part in (_item_label(db, from_parent_id), _location_label(db, from_location_id))
        if part
    ]
    to_parts = [
        part
        for part in (_item_label(db, item.parent_id), _location_label(db, item.location_id))
        if part
    ]

    movement = Movement(
        item_id=item.id,
        from_parent_id=from_parent_id,
        to_parent_id=item.parent_id,
        from_location_id=from_location_id,
        to_location_id=item.location_id,
        from_label=" @ ".join(from_parts) or None,
        to_label=" @ ".join(to_parts) or None,
        note=_clean(note),
    )
    db.add(movement)
    return movement


def create(
    db: Session,
    *,
    name: str,
    description: str | None = None,
    notes: str | None = None,
    quantity: int = 1,
    can_contain_items: bool = False,
    parent_id: str | None = None,
    location_id: str | None = None,
    tags: list[str] | None = None,
    with_qr_label: bool = True,
) -> Item:
    name = _require_name(name)
    if quantity < 0:
        raise ValidationError("Quantity cannot be negative.")
    _validate_parent(db, None, parent_id)
    _validate_location(db, location_id)

    item = Item(
        name=name,
        description=_clean(description),
        notes=_clean(notes),
        quantity=quantity,
        can_contain_items=can_contain_items,
        parent_id=parent_id,
        location_id=location_id,
    )
    item.tags = tag_service.resolve(db, tags or [])
    db.add(item)
    db.flush()

    _record_movement(
        db,
        item,
        from_parent_id=None,
        from_location_id=None,
        note="Item created",
    )
    if with_qr_label:
        # The intrinsic label carries the item identifier itself, so the printed
        # sticker stays valid no matter how the item is later renamed or moved.
        label_service.create(db, item, code=item.id, label_type="qr", note="Primary QR label")
    db.flush()
    return item


def update(
    db: Session,
    item: Item,
    *,
    name: str | None = None,
    description: str | None = None,
    notes: str | None = None,
    quantity: int | None = None,
    can_contain_items: bool | None = None,
    parent_id: str | None = None,
    location_id: str | None = None,
    tags: list[str] | None = None,
    move_note: str | None = None,
    unset: set[str] | None = None,
) -> Item:
    """Apply a partial update.

    Fields left as None are untouched. To clear a nullable field, name it in `unset`.
    """
    unset = unset or set()
    from_parent_id = item.parent_id
    from_location_id = item.location_id

    if name is not None:
        item.name = _require_name(name)
    if description is not None or "description" in unset:
        item.description = _clean(description)
    if notes is not None or "notes" in unset:
        item.notes = _clean(notes)
    if quantity is not None:
        if quantity < 0:
            raise ValidationError("Quantity cannot be negative.")
        item.quantity = quantity

    if can_contain_items is not None and can_contain_items != item.can_contain_items:
        if not can_contain_items and item.children:
            raise Conflict(
                f"{item.name} still holds {len(item.children)} item(s); "
                "move them out before clearing the container flag."
            )
        item.can_contain_items = can_contain_items

    if parent_id is not None or "parent_id" in unset:
        target = None if "parent_id" in unset else parent_id
        _validate_parent(db, item, target)
        item.parent_id = target

    if location_id is not None or "location_id" in unset:
        target = None if "location_id" in unset else location_id
        _validate_location(db, target)
        item.location_id = target

    if tags is not None:
        item.tags = tag_service.resolve(db, tags)

    db.flush()
    _record_movement(
        db,
        item,
        from_parent_id=from_parent_id,
        from_location_id=from_location_id,
        note=move_note,
    )
    db.flush()
    return item


def move(
    db: Session,
    item: Item,
    *,
    parent_id: str | None,
    location_id: str | None,
    note: str | None = None,
) -> Item:
    """Move an item, clearing whichever target was not supplied."""
    return update(
        db,
        item,
        parent_id=parent_id,
        location_id=location_id,
        move_note=note,
        unset={
            *(() if parent_id else ("parent_id",)),
            *(() if location_id else ("location_id",)),
        },
    )


def archive(db: Session, item: Item, *, cascade: bool = True) -> list[Item]:
    """Archive an item. Its contents are archived with it by default."""
    now = datetime.now(UTC)
    targets = [item]
    if cascade:
        ids = descendant_ids(db, item.id)
        if ids:
            targets.extend(db.scalars(select(Item).where(Item.id.in_(ids))).all())
    for target in targets:
        if target.archived_at is None:
            target.archived_at = now
    db.flush()
    return targets


def restore(db: Session, item: Item) -> Item:
    item.archived_at = None
    # An archived container should not silently hold a restored item.
    if item.parent is not None and item.parent.is_archived:
        from_parent_id = item.parent_id
        item.parent_id = None
        db.flush()
        _record_movement(
            db,
            item,
            from_parent_id=from_parent_id,
            from_location_id=item.location_id,
            note="Detached on restore: container is archived",
        )
    db.flush()
    return item


def delete(db: Session, item: Item) -> None:
    """Permanently delete an item. Contents are detached, never destroyed."""
    for child in list(item.children):
        child.parent = None
        db.add(
            Movement(
                item_id=child.id,
                from_parent_id=item.id,
                to_parent_id=None,
                from_location_id=child.location_id,
                to_location_id=child.location_id,
                from_label=item.name,
                to_label=None,
                note=f"Container {item.name} was deleted",
            )
        )
    db.flush()
    db.delete(item)
    db.flush()


def counts(db: Session) -> dict[str, int]:
    """Headline numbers for the dashboard."""
    active = Item.archived_at.is_(None)
    return {
        "items": db.scalar(select(func.count()).select_from(Item).where(active)) or 0,
        "containers": db.scalar(
            select(func.count())
            .select_from(Item)
            .where(active, Item.can_contain_items.is_(True))
        )
        or 0,
        "archived": db.scalar(
            select(func.count()).select_from(Item).where(Item.archived_at.is_not(None))
        )
        or 0,
        "unplaced": db.scalar(
            select(func.count())
            .select_from(Item)
            .where(active, Item.parent_id.is_(None), Item.location_id.is_(None))
        )
        or 0,
        "locations": db.scalar(select(func.count()).select_from(Location)) or 0,
    }


def recent(db: Session, limit: int = 8) -> list[Item]:
    return list(
        db.scalars(
            select(Item)
            .where(Item.archived_at.is_(None))
            .order_by(Item.updated_at.desc())
            .limit(limit)
        ).unique()
    )


def recent_movements(db: Session, limit: int = 10) -> list[Movement]:
    return list(
        db.scalars(
            select(Movement)
            .order_by(Movement.created_at.desc(), Movement.id.desc())
            .limit(limit)
        ).all()
    )


def container_options(db: Session, *, exclude_item_id: str | None = None) -> list[Item]:
    """Containers eligible as a parent, excluding an item and its own subtree."""
    query = select(Item).where(
        Item.can_contain_items.is_(True), Item.archived_at.is_(None)
    )
    blocked: set[str] = set()
    if exclude_item_id:
        blocked = {exclude_item_id, *descendant_ids(db, exclude_item_id)}
        query = query.where(Item.id.not_in(blocked))
    rows = list(db.scalars(query).unique())
    rows.sort(key=lambda row: row.path_label.lower())
    return rows
