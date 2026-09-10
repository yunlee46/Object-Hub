"""Arbitrary tags, addressed by a normalised slug so casing never duplicates a tag."""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Item, ItemTag, Tag
from app.services.errors import NotFound, ValidationError

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

# A stable, colour-blind-safe rotation used when a tag has no explicit colour.
PALETTE = (
    "#4f7cff",
    "#00a3a3",
    "#c9761d",
    "#8b5cf6",
    "#d1495b",
    "#2f8f4e",
    "#0e7490",
    "#a3801a",
)


def slugify(name: str) -> str:
    return _SLUG_STRIP.sub("-", name.strip().lower()).strip("-")


def parse(raw: str | list[str] | None) -> list[str]:
    """Accept a comma-separated string or a list, and return clean tag names."""
    if raw is None:
        return []
    parts = raw.split(",") if isinstance(raw, str) else list(raw)
    seen: dict[str, str] = {}
    for part in parts:
        name = part.strip()
        if not name:
            continue
        slug = slugify(name)
        if slug and slug not in seen:
            seen[slug] = name[:80]
    return list(seen.values())


def resolve(db: Session, names: list[str] | str | None) -> list[Tag]:
    """Return tag rows for the given names, creating any that do not exist yet."""
    resolved: list[Tag] = []
    for name in parse(names):
        slug = slugify(name)
        tag = db.scalar(select(Tag).where(Tag.slug == slug))
        if tag is None:
            tag = Tag(name=name, slug=slug, color=PALETTE[len(slug) % len(PALETTE)])
            db.add(tag)
            db.flush()
        resolved.append(tag)
    return resolved


def get(db: Session, tag_id: str) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise NotFound("That tag does not exist.")
    return tag


def get_by_slug(db: Session, slug: str) -> Tag:
    tag = db.scalar(select(Tag).where(Tag.slug == slugify(slug)))
    if tag is None:
        raise NotFound("That tag does not exist.")
    return tag


def rename(db: Session, tag: Tag, name: str) -> Tag:
    name = name.strip()
    if not name:
        raise ValidationError("A tag needs a name.")
    slug = slugify(name)
    if not slug:
        raise ValidationError("That tag name has no usable characters.")
    clash = db.scalar(select(Tag).where(Tag.slug == slug, Tag.id != tag.id))
    if clash is not None:
        raise ValidationError(f"A tag called {clash.name} already exists.")
    tag.name = name[:80]
    tag.slug = slug
    db.flush()
    return tag


def delete(db: Session, tag: Tag) -> None:
    db.delete(tag)
    db.flush()


def with_counts(db: Session) -> list[tuple[Tag, int]]:
    """Every tag with the number of active items carrying it, most used first."""
    used = (
        select(ItemTag.tag_id, func.count(ItemTag.item_id).label("total"))
        .join(Item, Item.id == ItemTag.item_id)
        .where(Item.archived_at.is_(None))
        .group_by(ItemTag.tag_id)
        .subquery()
    )
    rows = db.execute(
        select(Tag, func.coalesce(used.c.total, 0))
        .outerjoin(used, used.c.tag_id == Tag.id)
        .order_by(func.coalesce(used.c.total, 0).desc(), Tag.name)
    ).all()
    return [(row[0], int(row[1])) for row in rows]
