"""End-to-end coverage of the HTML UI and the JSON API."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import items as item_service
from app.services import locations as location_service


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_every_page_renders(client: TestClient, db: Session) -> None:
    location = location_service.create(db, name="Garage")
    box = item_service.create(
        db, name="Cabinet", can_contain_items=True, location_id=location.id
    )
    item = item_service.create(db, name="Screwdriver", parent_id=box.id, tags=["tools"])
    db.commit()

    for path in (
        "/",
        "/items",
        "/items?q=screw",
        "/items?containers_only=1",
        "/items?archived=1",
        "/items/new",
        f"/items/{item.id}",
        f"/items/{item.id}/edit",
        "/locations",
        "/tags",
        "/scan",
        "/labels/print",
        f"/labels/print?id={item.id}",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "text/html" in response.headers["content-type"]


def test_creating_an_item_through_the_form_redirects_to_it(client: TestClient) -> None:
    response = client.post(
        "/items",
        data={
            "name": "Label printer",
            "description": "Brother QL-800",
            "notes": "",
            "quantity": "1",
            "can_contain_items": "1",
            "parent_id": "",
            "location_id": "",
            "tags": "office, printing",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert "Label printer" in detail.text
    assert "Brother QL-800" in detail.text
    assert "printing" in detail.text


def test_a_domain_error_renders_a_page_for_the_ui(client: TestClient, db: Session) -> None:
    book = item_service.create(db, name="Book")
    db.commit()

    response = client.post(
        "/items",
        data={"name": "Bookmark", "quantity": "1", "parent_id": book.id},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert "not marked as able to contain items" in response.text


def test_a_domain_error_returns_json_for_the_api(client: TestClient, db: Session) -> None:
    book = item_service.create(db, name="Book")
    db.commit()

    response = client.post("/api/items", json={"name": "Bookmark", "parent_id": book.id})

    assert response.status_code == 422
    assert "contain items" in response.json()["detail"]


def test_missing_item_is_a_clean_404(client: TestClient) -> None:
    assert client.get("/items/does-not-exist").status_code == 404
    assert client.get("/api/items/does-not-exist").status_code == 404


def test_qr_label_resolves_to_the_item(client: TestClient, db: Session) -> None:
    item = item_service.create(db, name="Tripod")
    db.commit()

    response = client.get(f"/l/{item.id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/items/{item.id}"


def test_an_unknown_code_offers_to_link_it(client: TestClient) -> None:
    response = client.get("/scan?code=UNKNOWN-CODE", follow_redirects=True)

    assert response.status_code == 200
    assert "UNKNOWN-CODE" in response.text
    assert "Nothing is linked to" in response.text


def test_scan_endpoint_reports_resolution(client: TestClient, db: Session) -> None:
    item = item_service.create(db, name="Drone")
    db.commit()

    found = client.post("/api/scan", json={"code": f"http://nas.local/l/{item.id}"}).json()
    missing = client.post("/api/scan", json={"code": "nope"}).json()

    assert found["found"] is True
    assert found["item"]["name"] == "Drone"
    assert found["url"] == f"/items/{item.id}"
    assert missing["found"] is False


def test_qr_endpoints_serve_images(client: TestClient, db: Session) -> None:
    item = item_service.create(db, name="Thing")
    db.commit()

    svg = client.get(f"/api/qr/{item.id}.svg")
    png = client.get(f"/api/qr/{item.id}.png")

    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert png.headers["content-type"] == "image/png"


def test_api_crud_round_trip(client: TestClient) -> None:
    created = client.post(
        "/api/items",
        json={"name": "Suitcase", "can_contain_items": True, "tags": ["travel"]},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]

    inside = client.post("/api/items", json={"name": "Passport", "parent_id": item_id})
    assert inside.status_code == 201

    detail = client.get(f"/api/items/{item_id}").json()
    assert [child["name"] for child in detail["children"]] == ["Passport"]
    assert [tag["slug"] for tag in detail["tags"]] == ["travel"]

    renamed = client.patch(f"/api/items/{item_id}", json={"name": "Cabin bag"})
    assert renamed.json()["name"] == "Cabin bag"

    listing = client.get("/api/items", params={"q": "cabin"}).json()
    assert listing["total"] == 1

    assert client.post(f"/api/items/{item_id}/archive").status_code == 200
    assert client.get("/api/items").json()["total"] == 0
    assert client.post(f"/api/items/{item_id}/restore").status_code == 200

    assert client.delete(f"/api/items/{item_id}").status_code == 204
    assert client.get(f"/api/items/{item_id}").status_code == 404


def test_api_move_records_history(client: TestClient) -> None:
    box = client.post("/api/items", json={"name": "Box", "can_contain_items": True}).json()
    item = client.post("/api/items", json={"name": "Cable"}).json()

    moved = client.post(
        f"/api/items/{item['id']}/move",
        json={"parent_id": box["id"], "note": "Tidied up"},
    ).json()

    assert moved["parent_id"] == box["id"]
    assert moved["movements"][0]["note"] == "Tidied up"
    assert moved["movements"][0]["to_label"] == "Box"


def test_locations_api_round_trip(client: TestClient) -> None:
    house = client.post("/api/locations", json={"name": "House"}).json()
    garage = client.post(
        "/api/locations", json={"name": "Garage", "parent_id": house["id"]}
    ).json()

    assert garage["path_label"] == "House / Garage"

    listing = client.get("/api/locations").json()
    assert {row["name"] for row in listing} == {"House", "Garage"}

    assert client.delete(f"/api/locations/{garage['id']}").status_code == 204
    assert len(client.get("/api/locations").json()) == 1


def test_photo_upload_stores_a_thumbnail_and_sets_primary(
    client: TestClient, png_bytes: bytes
) -> None:
    item = client.post("/api/items", json={"name": "Camera"}).json()

    upload = client.post(
        f"/api/items/{item['id']}/photos",
        files={"file": ("shot.png", png_bytes, "image/png")},
    )

    assert upload.status_code == 201
    photo = upload.json()
    assert photo["is_primary"] is True
    assert photo["width"] == 60

    assert client.get(f"/api/photos/{photo['id']}").status_code == 200
    assert client.get(f"/api/photos/{photo['id']}?thumb=true").status_code == 200

    assert client.delete(f"/api/photos/{photo['id']}").status_code == 204
    assert client.get(f"/api/photos/{photo['id']}").status_code == 404


def test_a_file_that_is_not_an_image_is_rejected(client: TestClient) -> None:
    item = client.post("/api/items", json={"name": "Camera"}).json()

    response = client.post(
        f"/api/items/{item['id']}/photos",
        files={"file": ("payload.png", b"this is not a png", "image/png")},
    )

    assert response.status_code == 422
    assert "could not be read as an image" in response.json()["detail"]


def test_uploading_through_the_item_form(client: TestClient, png_bytes: bytes) -> None:
    response = client.post(
        "/items",
        data={"name": "Tripod", "quantity": "1"},
        files=[("photos", ("a.png", png_bytes, "image/png"))],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "1 photo(s) added" in response.text
