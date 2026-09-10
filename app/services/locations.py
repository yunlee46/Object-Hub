"""Locations: a hierarchy of physical places, independent of item containment."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Item, Location
from app.services.errors import NotFound, ValidationError

MAX_DEPTH = 64


def get(db: Session, location_id: str) -> Location:
    location = db.get(Location, location_id)
    if location is None:
        raise NotFound("That location does not exist.")
    return location


def all_ordered(db: Session) -> list[Location]:
    """Every location, sorted by full path so parents precede their children."""
    rows = list(db.scalars(select(Location)).unique())
    rows.sort(key=lambda row: row.path_label.lower())
    return rows


def descendant_ids(db: Session, location_id: str) -> set[str]:
    found: set[str] = set()
    frontier = [location_id]
    while frontier:
        rows = db.scalars(select(Location.id).where(Location.parent_id.in_(frontier))).all()
        fresh = [row for row in rows if row not in found]
        found.update(fresh)
        frontier = fresh
    return found


def _validate_parent(db: Session, location: Location | None, parent_id: str | None) -> None:
    if parent_id is None:
        return
    parent = db.get(Location, parent_id)
    if parent is None:
        raise ValidationError("The chosen parent location does not exist.")
    if location is None:
        return
    if parent.id == location.id:
        raise ValidationError("A location cannot be inside itself.")
    if parent.id in descendant_ids(db, location.id):
        raise ValidationError(
            f"{parent.name} is already inside {location.name}, so that would create a loop."
        )


def create(
    db: Session, *, name: str, parent_id: str | None = None, notes: str | None = None
) -> Location:
    name = (name or "").strip()
    if not name:
        raise ValidationError("A location needs a name.")
    _validate_parent(db, None, parent_id)
    location = Location(name=name[:200], parent_id=parent_id, notes=(notes or "").strip() or None)
    db.add(location)
    db.flush()
    return location


def update(
    db: Session,
    location: Location,
    *,
    name: str | None = None,
    parent_id: str | None = None,
    notes: str | None = None,
    unset: set[str] | None = None,
) -> Location:
    unset = unset or set()
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("A location needs a name.")
        location.name = cleaned[:200]
    if notes is not None or "notes" in unset:
        location.notes = (notes or "").strip() or None
    if parent_id is not None or "parent_id" in unset:
        target = None if "parent_id" in unset else parent_id
        _validate_parent(db, location, target)
        location.parent_id = target
    db.flush()
    return location


def delete(db: Session, location: Location) -> None:
    """Delete a location. Child locations and items are detached, never deleted.

    Reassignment goes through the relationships rather than the raw foreign keys, so
    the deleted row is removed from the in-session collections too. Setting only the
    key would let the unit of work null out the children it still believes it owns.
    """
    parent = location.parent
    for child in list(location.children):
        child.parent = parent
    for item in list(location.items):
        item.location = None
    db.flush()
    db.delete(location)
    db.flush()


def item_counts(db: Session) -> dict[str, int]:
    """Active item count per location, counting only items placed there directly."""
    rows = db.execute(
        select(Item.location_id, func.count(Item.id))
        .where(Item.archived_at.is_(None), Item.location_id.is_not(None))
        .group_by(Item.location_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def tree(db: Session) -> list[tuple[Location, int]]:
    """Locations flattened depth first, each paired with its indentation depth."""
    rows = list(db.scalars(select(Location)).unique())
    by_parent: dict[str | None, list[Location]] = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)
    for group in by_parent.values():
        group.sort(key=lambda row: row.name.lower())

    known = {row.id for row in rows}
    ordered: list[tuple[Location, int]] = []
    seen: set[str] = set()

    def walk(parent_id: str | None, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        for node in by_parent.get(parent_id, []):
            if node.id in seen:
                continue
            seen.add(node.id)
            ordered.append((node, depth))
            walk(node.id, depth + 1)

    walk(None, 0)
    # A location whose parent was removed out of band still deserves to be listed.
    for row in rows:
        if row.id not in seen and row.parent_id not in known:
            ordered.append((row, 0))
    return ordered
