"""Initial schema: locations, items, tags, photos, labels, movements.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(26)

# Every table carries the same timestamp columns; declaring them once keeps the
# migration readable and guarantees they stay identical across tables.


def _created_at(index: bool = False) -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
        index=index,
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", ID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("parent_id", ID, sa.ForeignKey("locations.id", ondelete="SET NULL")),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_locations_name", "locations", ["name"])
    op.create_index("ix_locations_parent_id", "locations", ["parent_id"])

    op.create_table(
        "tags",
        sa.Column("id", ID, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("color", sa.String(20)),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_tags_slug", "tags", ["slug"], unique=True)

    op.create_table(
        "items",
        sa.Column("id", ID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("can_contain_items", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parent_id", ID, sa.ForeignKey("items.id", ondelete="SET NULL")),
        sa.Column("location_id", ID, sa.ForeignKey("locations.id", ondelete="SET NULL")),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_items_name", "items", ["name"])
    op.create_index("ix_items_parent_id", "items", ["parent_id"])
    op.create_index("ix_items_location_id", "items", ["location_id"])
    op.create_index("ix_items_archived_at", "items", ["archived_at"])

    op.create_table(
        "item_tags",
        sa.Column("item_id", ID, sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", ID, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "photos",
        sa.Column("id", ID, primary_key=True),
        sa.Column("item_id", ID, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("original_name", sa.String(255)),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        _created_at(),
    )
    op.create_index("ix_photos_item_id", "photos", ["item_id"])

    op.create_table(
        "labels",
        sa.Column("id", ID, primary_key=True),
        sa.Column("item_id", ID, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(200), nullable=False),
        sa.Column("label_type", sa.String(20), nullable=False, server_default="qr"),
        sa.Column("note", sa.String(255)),
        _created_at(),
        sa.UniqueConstraint("code", name="uq_labels_code"),
    )
    op.create_index("ix_labels_item_id", "labels", ["item_id"])

    op.create_table(
        "movements",
        sa.Column("id", ID, primary_key=True),
        sa.Column("item_id", ID, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_parent_id", ID),
        sa.Column("to_parent_id", ID),
        sa.Column("from_location_id", ID),
        sa.Column("to_location_id", ID),
        sa.Column("from_label", sa.String(400)),
        sa.Column("to_label", sa.String(400)),
        sa.Column("note", sa.String(400)),
        _created_at(index=True),
    )
    op.create_index("ix_movements_item_id", "movements", ["item_id"])


def downgrade() -> None:
    op.drop_table("movements")
    op.drop_table("labels")
    op.drop_table("photos")
    op.drop_table("item_tags")
    op.drop_table("items")
    op.drop_table("tags")
    op.drop_table("locations")
