"""Request and response models for the JSON API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    color: str | None = None


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, max_length=20)


class LocationRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    path_label: str


class LocationOut(LocationRef):
    parent_id: str | None = None
    notes: str | None = None
    created_at: datetime


class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None
    notes: str | None = None


class LocationPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    parent_id: str | None = None
    notes: str | None = None
    clear_parent: bool = False


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    width: int
    height: int
    size_bytes: int
    is_primary: bool
    created_at: datetime


class LabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    label_type: str
    note: str | None = None
    created_at: datetime


class LabelIn(BaseModel):
    code: str = Field(min_length=1, max_length=200)
    label_type: str = "manufacturer"
    note: str | None = Field(default=None, max_length=255)


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_label: str | None = None
    to_label: str | None = None
    note: str | None = None
    created_at: datetime


class ItemRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    can_contain_items: bool


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    notes: str | None = None
    quantity: int
    can_contain_items: bool
    parent_id: str | None = None
    location_id: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    tags: list[TagOut] = []
    photos: list[PhotoOut] = []
    location: LocationRef | None = None


class ItemDetail(ItemOut):
    path: list[ItemRef] = []
    children: list[ItemRef] = []
    labels: list[LabelOut] = []
    movements: list[MovementOut] = []
    effective_location: LocationRef | None = None


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    notes: str | None = None
    quantity: int = Field(default=1, ge=0)
    can_contain_items: bool = False
    parent_id: str | None = None
    location_id: str | None = None
    tags: list[str] = []


class ItemPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    notes: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    can_contain_items: bool | None = None
    parent_id: str | None = None
    location_id: str | None = None
    tags: list[str] | None = None
    move_note: str | None = None
    clear_parent: bool = False
    clear_location: bool = False


class MoveIn(BaseModel):
    parent_id: str | None = None
    location_id: str | None = None
    note: str | None = Field(default=None, max_length=400)


class ItemPage(BaseModel):
    items: list[ItemOut]
    total: int
    page: int
    per_page: int
    pages: int


class ScanIn(BaseModel):
    code: str = Field(min_length=1, max_length=400)


class ScanOut(BaseModel):
    code: str
    found: bool
    item: ItemOut | None = None
    url: str | None = None
