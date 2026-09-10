"""SQLAlchemy models.

Column types are deliberately portable so the test suite can run on SQLite while
production runs on PostgreSQL.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.services.ids import new_id

ID = String(26)


def _utcnow() -> datetime:
    """Row timestamps are generated in Python, not by the database.

    PostgreSQL resolves now() once per transaction, so several rows written in one
    request would share a timestamp and history ordering would be ambiguous. A
    Python call gives each row microsecond resolution. The server default remains as
    a safety net for rows inserted outside the application.
    """
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class Location(TimestampMixin, Base):
    """A physical place. Locations form their own hierarchy."""

    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(
        ID, ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )

    parent: Mapped[Location | None] = relationship(
        remote_side=[id], back_populates="children", lazy="joined", join_depth=2
    )
    children: Mapped[list[Location]] = relationship(
        back_populates="parent", order_by="Location.name"
    )
    items: Mapped[list[Item]] = relationship(back_populates="location")

    __table_args__ = (Index("ix_locations_name", "name"),)

    @property
    def path(self) -> list[Location]:
        chain: list[Location] = []
        node: Location | None = self
        seen: set[str] = set()
        while node is not None and node.id not in seen:
            seen.add(node.id)
            chain.append(node)
            node = node.parent
        return list(reversed(chain))

    @property
    def path_label(self) -> str:
        return " / ".join(node.name for node in self.path)


class ItemTag(Base):
    """Association table between items and tags."""

    __tablename__ = "item_tags"

    item_id: Mapped[str] = mapped_column(
        ID, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        ID, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class Tag(TimestampMixin, Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    color: Mapped[str | None] = mapped_column(String(20))

    items: Mapped[list[Item]] = relationship(
        secondary="item_tags", back_populates="tags", order_by="Item.name"
    )


class Item(TimestampMixin, Base):
    """Any tracked physical object.

    A container is not a separate entity: it is an item with can_contain_items set.
    """

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    can_contain_items: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    parent_id: Mapped[str | None] = mapped_column(
        ID, ForeignKey("items.id", ondelete="SET NULL"), index=True
    )
    location_id: Mapped[str | None] = mapped_column(
        ID, ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    parent: Mapped[Item | None] = relationship(
        remote_side=[id], back_populates="children", lazy="joined", join_depth=2
    )
    children: Mapped[list[Item]] = relationship(back_populates="parent", order_by="Item.name")
    location: Mapped[Location | None] = relationship(back_populates="items", lazy="joined")
    tags: Mapped[list[Tag]] = relationship(
        secondary="item_tags", back_populates="items", order_by="Tag.name", lazy="selectin"
    )
    photos: Mapped[list[Photo]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="Photo.created_at, Photo.id",
        lazy="selectin",
    )
    labels: Mapped[list[Label]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Label.created_at, Label.id"
    )
    movements: Mapped[list[Movement]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="Movement.created_at.desc(), Movement.id.desc()",
    )

    __table_args__ = (Index("ix_items_name", "name"),)

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def path(self) -> list[Item]:
        """The containment path, from the outermost ancestor down to this item."""
        chain: list[Item] = []
        node: Item | None = self
        seen: set[str] = set()
        while node is not None and node.id not in seen:
            seen.add(node.id)
            chain.append(node)
            node = node.parent
        return list(reversed(chain))

    @property
    def path_label(self) -> str:
        return " / ".join(node.name for node in self.path)

    @property
    def primary_photo(self) -> Photo | None:
        for photo in self.photos:
            if photo.is_primary:
                return photo
        return self.photos[0] if self.photos else None

    @property
    def effective_location(self) -> Location | None:
        """Own location, otherwise inherited from the nearest ancestor that has one."""
        for node in reversed(self.path):
            if node.location is not None:
                return node.location
        return None


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    item_id: Mapped[str] = mapped_column(
        ID, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(120), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )

    item: Mapped[Item] = relationship(back_populates="photos")


class Label(Base):
    """An opaque code that resolves to exactly one item."""

    __tablename__ = "labels"

    QR = "qr"
    DATAMATRIX = "datamatrix"
    CODE128 = "code128"
    MANUFACTURER = "manufacturer"
    TYPES = (QR, DATAMATRIX, CODE128, MANUFACTURER)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    item_id: Mapped[str] = mapped_column(
        ID, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(200), nullable=False)
    label_type: Mapped[str] = mapped_column(String(20), nullable=False, default=QR)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )

    item: Mapped[Item] = relationship(back_populates="labels")

    __table_args__ = (UniqueConstraint("code", name="uq_labels_code"),)


class Movement(Base):
    """An append-only record of a parent or location change.

    Human-readable labels are denormalised alongside the identifiers so history stays
    legible after a container or location is later renamed or removed.
    """

    __tablename__ = "movements"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    item_id: Mapped[str] = mapped_column(
        ID, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_parent_id: Mapped[str | None] = mapped_column(ID)
    to_parent_id: Mapped[str | None] = mapped_column(ID)
    from_location_id: Mapped[str | None] = mapped_column(ID)
    to_location_id: Mapped[str | None] = mapped_column(ID)
    from_label: Mapped[str | None] = mapped_column(String(400))
    to_label: Mapped[str | None] = mapped_column(String(400))
    note: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    item: Mapped[Item] = relationship(back_populates="movements")
