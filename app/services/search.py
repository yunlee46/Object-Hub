"""Item search and filtering.

Deliberately built on portable SQL: ILIKE-style matching over the fields a person
would actually remember, plus tag, location, and label lookups. No search service is
introduced, because a household inventory does not justify one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Item, ItemTag, Label, Tag
from app.services import locations as location_service
from app.services import tags as tag_service

SORTS = {
    "recent": "Recently updated",
    "name": "Name",
    "created": "Newest first",
    "quantity": "Quantity",
}


@dataclass(slots=True)
class Query:
    text: str = ""
    location_id: str | None = None
    parent_id: str | None = None
    tag_slugs: list[str] = field(default_factory=list)
    containers_only: bool = False
    unplaced_only: bool = False
    include_archived: bool = False
    archived_only: bool = False
    sort: str = "recent"
    page: int = 1
    per_page: int = 50
    include_sublocations: bool = True
    include_contained: bool = True

    @property
    def is_filtered(self) -> bool:
        return bool(
            self.text
            or self.location_id
            or self.parent_id
            or self.tag_slugs
            or self.containers_only
            or self.unplaced_only
            or self.archived_only
        )


@dataclass(slots=True)
class Results:
    items: list[Item]
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def start(self) -> int:
        return 0 if not self.total else (self.page - 1) * self.per_page + 1

    @property
    def end(self) -> int:
        return min(self.total, self.page * self.per_page)


def _items_at_locations(db: Session, location_ids: set[str]) -> set[str]:
    """Identifiers of every item whose effective location is one of these locations.

    An item placed directly at a location is included, and so is anything nested
    inside it that has no location of its own, because that is what inheritance
    means: a screwdriver in a tool box in the garage is in the garage. A descendant
    that sets its own location overrides the inherited one and is excluded here, along
    with its own subtree.

    Resolved in Python rather than as a recursive CTE to stay portable across
    PostgreSQL and the SQLite the test suite uses. The result set is bounded by the
    size of a household inventory.
    """
    seeds = set(db.scalars(select(Item.id).where(Item.location_id.in_(location_ids))).all())
    found = set(seeds)
    frontier = list(seeds)
    while frontier:
        rows = db.scalars(
            select(Item.id).where(Item.parent_id.in_(frontier), Item.location_id.is_(None))
        ).all()
        fresh = [row for row in rows if row not in found]
        found.update(fresh)
        frontier = fresh
    return found


def _apply_filters(db: Session, statement: Select, query: Query) -> Select:
    if query.archived_only:
        statement = statement.where(Item.archived_at.is_not(None))
    elif not query.include_archived:
        statement = statement.where(Item.archived_at.is_(None))

    text = query.text.strip()
    if text:
        pattern = f"%{text.lower()}%"
        matches_label = select(Label.item_id).where(func.lower(Label.code) == text.lower())
        matches_tag = (
            select(ItemTag.item_id)
            .join(Tag, Tag.id == ItemTag.tag_id)
            .where(func.lower(Tag.name).like(pattern))
        )
        statement = statement.where(
            or_(
                func.lower(Item.name).like(pattern),
                func.lower(func.coalesce(Item.description, "")).like(pattern),
                func.lower(func.coalesce(Item.notes, "")).like(pattern),
                Item.id.in_(matches_label),
                Item.id.in_(matches_tag),
            )
        )

    if query.location_id:
        location_ids = {query.location_id}
        if query.include_sublocations:
            location_ids |= location_service.descendant_ids(db, query.location_id)
        if query.include_contained:
            statement = statement.where(Item.id.in_(_items_at_locations(db, location_ids)))
        else:
            statement = statement.where(Item.location_id.in_(location_ids))

    if query.parent_id:
        statement = statement.where(Item.parent_id == query.parent_id)

    for slug in query.tag_slugs:
        # Chained subqueries so several tags narrow the result rather than widen it.
        matching = (
            select(ItemTag.item_id)
            .join(Tag, Tag.id == ItemTag.tag_id)
            .where(Tag.slug == tag_service.slugify(slug))
        )
        statement = statement.where(Item.id.in_(matching))

    if query.containers_only:
        statement = statement.where(Item.can_contain_items.is_(True))

    if query.unplaced_only:
        statement = statement.where(Item.parent_id.is_(None), Item.location_id.is_(None))

    return statement


def _apply_sort(statement: Select, sort: str) -> Select:
    if sort == "name":
        return statement.order_by(func.lower(Item.name))
    if sort == "created":
        return statement.order_by(Item.created_at.desc())
    if sort == "quantity":
        return statement.order_by(Item.quantity.desc(), func.lower(Item.name))
    return statement.order_by(Item.updated_at.desc())


def run(db: Session, query: Query) -> Results:
    page = max(1, query.page)
    per_page = max(1, min(query.per_page, 200))

    total = (
        db.scalar(_apply_filters(db, select(func.count(Item.id)).select_from(Item), query)) or 0
    )
    statement = _apply_sort(_apply_filters(db, select(Item), query), query.sort)
    rows = list(
        db.scalars(statement.offset((page - 1) * per_page).limit(per_page)).unique()
    )
    return Results(items=rows, total=total, page=page, per_page=per_page)


def suggest(db: Session, text: str, limit: int = 10) -> list[Item]:
    """Lightweight name-prefix suggestions for the move and quick-find widgets."""
    text = (text or "").strip()
    if not text:
        return []
    pattern = f"%{text.lower()}%"
    return list(
        db.scalars(
            select(Item)
            .where(Item.archived_at.is_(None), func.lower(Item.name).like(pattern))
            .order_by(func.lower(Item.name))
            .limit(limit)
        ).unique()
    )
