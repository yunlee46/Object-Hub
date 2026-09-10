"""Item lifecycle, containment rules, and movement history."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services import items as item_service
from app.services import locations as location_service
from app.services.errors import Conflict, NotFound, ValidationError


def test_create_assigns_stable_identifier_and_qr_label(db: Session) -> None:
    item = item_service.create(db, name="Anker charger")

    assert len(item.id) == 26
    assert [label.code for label in item.labels] == [item.id]
    assert item.labels[0].label_type == "qr"


def test_create_requires_a_name(db: Session) -> None:
    with pytest.raises(ValidationError):
        item_service.create(db, name="   ")


def test_containment_path_reads_outermost_first(db: Session) -> None:
    garage = item_service.create(db, name="Garage", can_contain_items=True)
    cabinet = item_service.create(db, name="Cabinet A", can_contain_items=True, parent_id=garage.id)
    toolbox = item_service.create(db, name="Tool Box", can_contain_items=True, parent_id=cabinet.id)
    driver = item_service.create(db, name="Screwdriver", parent_id=toolbox.id)

    assert driver.path_label == "Garage / Cabinet A / Tool Box / Screwdriver"


def test_parent_must_be_a_container(db: Session) -> None:
    book = item_service.create(db, name="Book")

    with pytest.raises(ValidationError, match="not marked as able to contain"):
        item_service.create(db, name="Bookmark", parent_id=book.id)


def test_item_cannot_be_its_own_parent(db: Session) -> None:
    box = item_service.create(db, name="Box", can_contain_items=True)

    with pytest.raises(ValidationError, match="cannot contain itself"):
        item_service.update(db, box, parent_id=box.id)


def test_cycles_are_rejected(db: Session) -> None:
    outer = item_service.create(db, name="Outer", can_contain_items=True)
    inner = item_service.create(db, name="Inner", can_contain_items=True, parent_id=outer.id)

    with pytest.raises(ValidationError, match="create a loop"):
        item_service.update(db, outer, parent_id=inner.id)


def test_deep_cycles_are_rejected(db: Session) -> None:
    a = item_service.create(db, name="A", can_contain_items=True)
    b = item_service.create(db, name="B", can_contain_items=True, parent_id=a.id)
    c = item_service.create(db, name="C", can_contain_items=True, parent_id=b.id)

    with pytest.raises(ValidationError, match="create a loop"):
        item_service.update(db, a, parent_id=c.id)


def test_container_flag_cannot_be_cleared_while_holding_items(db: Session) -> None:
    box = item_service.create(db, name="Box", can_contain_items=True)
    item_service.create(db, name="Cable", parent_id=box.id)
    db.refresh(box)

    with pytest.raises(Conflict, match="still holds"):
        item_service.update(db, box, can_contain_items=False)


def test_location_is_inherited_from_the_nearest_ancestor(db: Session) -> None:
    garage = location_service.create(db, name="Garage")
    cabinet = item_service.create(
        db, name="Cabinet", can_contain_items=True, location_id=garage.id
    )
    box = item_service.create(db, name="Box", can_contain_items=True, parent_id=cabinet.id)
    screw = item_service.create(db, name="Screw", parent_id=box.id)

    assert screw.location_id is None
    assert screw.effective_location is not None
    assert screw.effective_location.id == garage.id


def test_own_location_overrides_an_inherited_one(db: Session) -> None:
    garage = location_service.create(db, name="Garage")
    office = location_service.create(db, name="Office")
    cabinet = item_service.create(
        db, name="Cabinet", can_contain_items=True, location_id=garage.id
    )
    item = item_service.create(db, name="Stapler", parent_id=cabinet.id, location_id=office.id)

    assert item.effective_location is not None
    assert item.effective_location.id == office.id


def test_moving_records_history_with_readable_labels(db: Session) -> None:
    shelf = location_service.create(db, name="Shelf")
    box = item_service.create(db, name="Box", can_contain_items=True)
    item = item_service.create(db, name="Lens", location_id=shelf.id)

    item_service.move(db, item, parent_id=box.id, location_id=None, note="Packed away")
    db.refresh(item)

    latest = item.movements[0]
    assert latest.note == "Packed away"
    assert latest.from_label == "Shelf"
    assert latest.to_label == "Box"
    assert latest.to_parent_id == box.id
    assert latest.to_location_id is None


def test_history_is_not_written_when_nothing_moved(db: Session) -> None:
    item = item_service.create(db, name="Kettle")
    before = len(item.movements)

    item_service.update(db, item, name="Electric kettle")
    db.refresh(item)

    assert len(item.movements) == before


def test_renaming_keeps_earlier_history_readable(db: Session) -> None:
    box = item_service.create(db, name="Blue box", can_contain_items=True)
    item = item_service.create(db, name="Charger", parent_id=box.id)

    item_service.update(db, box, name="Green box")
    db.refresh(item)

    assert item.movements[-1].to_label == "Blue box"


def test_archiving_cascades_and_restore_detaches_from_archived_parent(db: Session) -> None:
    box = item_service.create(db, name="Box", can_contain_items=True)
    inner = item_service.create(db, name="Cable", parent_id=box.id)

    affected = item_service.archive(db, box)
    assert {row.id for row in affected} == {box.id, inner.id}

    item_service.restore(db, inner)
    db.refresh(inner)

    assert inner.archived_at is None
    assert inner.parent_id is None
    assert "container is archived" in (inner.movements[0].note or "")


def test_delete_detaches_contents_rather_than_destroying_them(db: Session) -> None:
    box = item_service.create(db, name="Box", can_contain_items=True)
    inner = item_service.create(db, name="Cable", parent_id=box.id)

    item_service.delete(db, box)

    survivor = item_service.get(db, inner.id)
    assert survivor.parent_id is None
    with pytest.raises(NotFound):
        item_service.get(db, box.id)


def test_container_options_exclude_the_item_and_its_subtree(db: Session) -> None:
    outer = item_service.create(db, name="Outer", can_contain_items=True)
    inner = item_service.create(db, name="Inner", can_contain_items=True, parent_id=outer.id)
    other = item_service.create(db, name="Elsewhere", can_contain_items=True)

    options = {row.id for row in item_service.container_options(db, exclude_item_id=outer.id)}

    assert options == {other.id}
    assert inner.id not in options


def test_counts_summarise_the_collection(db: Session) -> None:
    location_service.create(db, name="Garage")
    box = item_service.create(db, name="Box", can_contain_items=True)
    item_service.create(db, name="Loose thing")
    archived = item_service.create(db, name="Old thing")
    item_service.archive(db, archived)

    counts = item_service.counts(db)

    assert counts["items"] == 2
    assert counts["containers"] == 1
    assert counts["archived"] == 1
    assert counts["unplaced"] == 2
    assert counts["locations"] == 1
    assert box.id
