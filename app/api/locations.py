"""JSON API for locations and tags."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Location
from app.schemas import LocationIn, LocationOut, LocationPatch, TagIn, TagOut
from app.services import locations as location_service
from app.services import tags as tag_service

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationOut])
def list_locations(db: Session = Depends(get_db)) -> list[Location]:
    return location_service.all_ordered(db)


@router.post("", response_model=LocationOut, status_code=201)
def create_location(payload: LocationIn, db: Session = Depends(get_db)) -> Location:
    return location_service.create(
        db, name=payload.name, parent_id=payload.parent_id, notes=payload.notes
    )


@router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: str, db: Session = Depends(get_db)) -> Location:
    return location_service.get(db, location_id)


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(
    location_id: str, payload: LocationPatch, db: Session = Depends(get_db)
) -> Location:
    location = location_service.get(db, location_id)
    return location_service.update(
        db,
        location,
        name=payload.name,
        parent_id=payload.parent_id,
        notes=payload.notes,
        unset={"parent_id"} if payload.clear_parent else set(),
    )


@router.delete("/{location_id}", status_code=204)
def delete_location(location_id: str, db: Session = Depends(get_db)) -> Response:
    location_service.delete(db, location_service.get(db, location_id))
    return Response(status_code=204)


tag_router = APIRouter(prefix="/tags", tags=["tags"])


@tag_router.get("", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)) -> list[TagOut]:
    return [TagOut.model_validate(tag) for tag, _ in tag_service.with_counts(db)]


@tag_router.post("", response_model=TagOut, status_code=201)
def create_tag(payload: TagIn, db: Session = Depends(get_db)) -> TagOut:
    tag = tag_service.resolve(db, [payload.name])[0]
    if payload.color:
        tag.color = payload.color
    return TagOut.model_validate(tag)


@tag_router.patch("/{tag_id}", response_model=TagOut)
def rename_tag(tag_id: str, payload: TagIn, db: Session = Depends(get_db)) -> TagOut:
    tag = tag_service.rename(db, tag_service.get(db, tag_id), payload.name)
    if payload.color:
        tag.color = payload.color
    return TagOut.model_validate(tag)


@tag_router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: str, db: Session = Depends(get_db)) -> Response:
    tag_service.delete(db, tag_service.get(db, tag_id))
    return Response(status_code=204)
