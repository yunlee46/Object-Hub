"""Search, filtering, tags, and locations."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services import items as item_service
from app.services import labels as label_service
from app.services import locations as location_service
from app.services import search as search_service
from app.services import tags as tag_service
from app.services.errors import ValidationError


def _names(results: search_service.Results) -> set[str]:
    return {item.name for item in results.items}


def test_text_search_covers_name_description_and_notes(db: Session) -> None:
    item_service.create(db, name="USB-C charger")
    item_service.create(db, name="Mystery brick", description="A 65W USB-C power supply")
    item_service.create(db, name="Notebook", notes="usb-c dongle lives in the sleeve")
    item_service.create(db, name="Kettle")

    results = search_service.run(db, search_service.Query(text="usb-c"))

    assert _names(results) == {"USB-C charger", "Mystery brick", "Notebook"}


def test_search_is_case_insensitive(db: Session) -> None:
    item_service.create(db, name="Screwdriver")

    assert search_service.run(db, search_service.Query(text="SCREW")).total == 1


def test_search_finds_an_item_by_its_label_code(db: Session) -> None:
    item = item_service.create(db, name="Battery")
    label_service.create(db, item, code="4006381333931", label_type="manufacturer")

    results = search_service.run(db, search_service.Query(text="4006381333931"))

    assert _names(results) == {"Battery"}


def test_search_finds_an_item_by_tag_name(db: Session) -> None:
    item_service.create(db, name="Lens", tags=["fragile", "photography"])
    item_service.create(db, name="Hammer")

    assert _names(search_service.run(db, search_service.Query(text="fragile"))) == {"Lens"}


def test_archived_items_are_hidden_unless_asked_for(db: Session) -> None:
    keep = item_service.create(db, name="Current thing")
    gone = item_service.create(db, name="Old thing")
    item_service.archive(db, gone)

    assert _names(search_service.run(db, search_service.Query())) == {keep.name}
    assert _names(search_service.run(db, search_service.Query(archived_only=True))) == {gone.name}
    assert (
        _names(search_service.run(db, search_service.Query(include_archived=True)))
        == {keep.name, gone.name}
    )


def test_location_filter_includes_sublocations(db: Session) -> None:
    house = location_service.create(db, name="House")
    garage = location_service.create(db, name="Garage", parent_id=house.id)
    item_service.create(db, name="Bike", location_id=garage.id)
    item_service.create(db, name="Sofa", location_id=house.id)

    everything = search_service.run(db, search_service.Query(location_id=house.id))
    just_house = search_service.run(
        db, search_service.Query(location_id=house.id, include_sublocations=False)
    )

    assert _names(everything) == {"Bike", "Sofa"}
    assert _names(just_house) == {"Sofa"}


def test_multiple_tags_narrow_the_results(db: Session) -> None:
    item_service.create(db, name="Camera lens", tags=["fragile", "photography"])
    item_service.create(db, name="Glass jar", tags=["fragile"])

    both = search_service.run(db, search_service.Query(tag_slugs=["fragile", "photography"]))
    one = search_service.run(db, search_service.Query(tag_slugs=["fragile"]))

    assert _names(both) == {"Camera lens"}
    assert _names(one) == {"Camera lens", "Glass jar"}


def test_container_and_unplaced_filters(db: Session) -> None:
    shelf = location_service.create(db, name="Shelf")
    box = item_service.create(db, name="Box", can_contain_items=True, location_id=shelf.id)
    item_service.create(db, name="Inside thing", parent_id=box.id)
    item_service.create(db, name="Floating thing")

    containers = search_service.run(db, search_service.Query(containers_only=True))
    unplaced = search_service.run(db, search_service.Query(unplaced_only=True))

    assert _names(containers) == {"Box"}
    assert _names(unplaced) == {"Floating thing"}


def test_pagination_reports_a_stable_window(db: Session) -> None:
    for index in range(7):
        item_service.create(db, name=f"Item {index:02d}")

    page_two = search_service.run(db, search_service.Query(sort="name", page=2, per_page=3))

    assert page_two.total == 7
    assert page_two.pages == 3
    assert [item.name for item in page_two.items] == ["Item 03", "Item 04", "Item 05"]
    assert (page_two.start, page_two.end) == (4, 6)
    assert page_two.has_prev and page_two.has_next


def test_tags_are_deduplicated_by_slug(db: Session) -> None:
    first = item_service.create(db, name="One", tags=["Photography"])
    second = item_service.create(db, name="Two", tags=["photography", "PHOTOGRAPHY "])

    assert len(second.tags) == 1
    assert first.tags[0].id == second.tags[0].id


def test_tag_counts_ignore_archived_items(db: Session) -> None:
    item_service.create(db, name="Live", tags=["shared"])
    archived = item_service.create(db, name="Dead", tags=["shared"])
    item_service.archive(db, archived)

    counts = dict((tag.slug, total) for tag, total in tag_service.with_counts(db))

    assert counts["shared"] == 1


def test_location_hierarchy_rejects_cycles(db: Session) -> None:
    house = location_service.create(db, name="House")
    garage = location_service.create(db, name="Garage", parent_id=house.id)

    with pytest.raises(ValidationError, match="create a loop"):
        location_service.update(db, house, parent_id=garage.id)


def test_deleting_a_location_detaches_items_and_reparents_children(db: Session) -> None:
    house = location_service.create(db, name="House")
    garage = location_service.create(db, name="Garage", parent_id=house.id)
    shelf = location_service.create(db, name="Shelf", parent_id=garage.id)
    item = item_service.create(db, name="Bike", location_id=garage.id)

    location_service.delete(db, garage)

    db.refresh(item)
    db.refresh(shelf)
    assert item.location_id is None
    assert shelf.parent_id == house.id
    assert item_service.get(db, item.id) is not None


def test_location_tree_is_depth_first_with_depths(db: Session) -> None:
    house = location_service.create(db, name="House")
    location_service.create(db, name="Garage", parent_id=house.id)
    location_service.create(db, name="Attic", parent_id=house.id)

    tree = [(location.name, depth) for location, depth in location_service.tree(db)]

    assert tree == [("House", 0), ("Attic", 1), ("Garage", 1)]


def test_location_filter_finds_items_that_inherit_the_location(db: Session) -> None:
    house = location_service.create(db, name="House")
    garage = location_service.create(db, name="Garage", parent_id=house.id)
    cabinet = item_service.create(
        db, name="Cabinet", can_contain_items=True, location_id=garage.id
    )
    toolbox = item_service.create(
        db, name="Tool Box", can_contain_items=True, parent_id=cabinet.id
    )
    item_service.create(db, name="Screwdriver", parent_id=toolbox.id)

    # Asking for the house finds everything nested inside things placed there.
    assert _names(search_service.run(db, search_service.Query(location_id=house.id))) == {
        "Cabinet",
        "Tool Box",
        "Screwdriver",
    }
    # Directly-placed only, for callers that want the narrow reading.
    assert _names(
        search_service.run(
            db, search_service.Query(location_id=garage.id, include_contained=False)
        )
    ) == {"Cabinet"}


def test_an_own_location_removes_an_item_from_its_containers_location(db: Session) -> None:
    garage = location_service.create(db, name="Garage")
    office = location_service.create(db, name="Office")
    cabinet = item_service.create(
        db, name="Cabinet", can_contain_items=True, location_id=garage.id
    )
    box = item_service.create(
        db, name="Loaned box", can_contain_items=True, parent_id=cabinet.id,
        location_id=office.id,
    )
    item_service.create(db, name="Stapler", parent_id=box.id)

    garage_items = _names(search_service.run(db, search_service.Query(location_id=garage.id)))
    office_items = _names(search_service.run(db, search_service.Query(location_id=office.id)))

    assert garage_items == {"Cabinet"}
    assert office_items == {"Loaned box", "Stapler"}
