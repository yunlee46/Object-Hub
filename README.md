# Object Hub

A self-hosted inventory for real-world things. Track what you own, which box it is in,
which room that box is in, and find it again by searching or by scanning a label with
your phone.

Runs as a two-container Docker Compose stack on a NAS. No cloud services, no
accounts, no internet connection required at runtime.

## Quick start

```bash
cp .env.example .env      # then change POSTGRES_PASSWORD
docker compose up -d --build
```

Open <http://localhost:8080>. Migrations run automatically before the server starts.

For development with hot reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## How it works

### Items and containers

Everything is an **item**: a charger, a book, a camera, a suitcase, a storage cabinet.
An item that can hold other items is marked as a **container**, which is all a
container is — there is no separate entity for boxes. Items nest arbitrarily:

```text
Garage
└── Cabinet A
    └── Tool Box
        └── Screwdriver
```

An item has at most one parent, cycles are rejected, and moving a container moves
everything inside it.

### Locations

**Locations** are physical places — house, garage, office, vehicle — and form their own
hierarchy, separate from item containment. An item can sit at a location directly, or
inherit one from the nearest ancestor that has one. So a screwdriver in a tool box in
a cabinet in the garage reports "Garage" without you having to say so twice.

Deleting a location never deletes items; they simply lose their location.

### Labels that never go stale

Every item receives a ULID at creation: opaque, URL-safe, sortable by creation time,
and permanent. Its QR code encodes only `/l/<identifier>` — never a name, never a
location. Rename the item, move it to a different room, put it in another box, and the
same printed sticker still resolves.

Scanning is also supported for codes a product already carries: link a manufacturer
barcode to an item and scanning it opens that item. Scanning an unknown code offers to
link it to something.

Print sheets from **Labels**, sized for A4 sticker stock at three across.

### Photos

Photos are stored on a local volume, never in the database. Uploads are validated by
decoding the image rather than trusting the declared content type, stored under a
generated name, EXIF-rotated, downscaled, and given a thumbnail for list views.

### History

Every change of container or location appends an immutable **movement** row recording
where the item came from, where it went, when, and an optional note. The human-readable
names are stored alongside the identifiers, so history stays legible even after a
container is renamed or deleted. History is only ever appended to.

## Scanning from a phone

Camera scanning uses the browser's built-in `BarcodeDetector`, so no decoder library
is downloaded and no image leaves the device. It needs a secure context: `localhost`
works directly, and a LAN deployment needs HTTPS or a tunnel such as Tailscale. Manual
code entry is always available, and every page works without JavaScript.

## Configuration

All settings have working defaults; see `.env.example`.

| Variable            | Default              | Purpose                                  |
| ------------------- | -------------------- | ---------------------------------------- |
| `POSTGRES_PASSWORD` | `objecthub`          | Database password — change this          |
| `APP_PORT`          | `8080`               | Host port for the UI                     |
| `APP_NAME`          | `Object Hub`         | Name shown in the interface              |
| `DATABASE_URL`      | compose-provided     | Only set when running outside Docker     |
| `DATA_DIR`          | `/data`              | Where photos and thumbnails are written  |
| `BASE_URL`          | empty                | Optional hint shown beside labels        |

QR payloads stay relative regardless of `BASE_URL`, so the same label works whether
you reach the app by LAN hostname, IP, or reverse proxy.

## JSON API

Every operation the UI performs is available under `/api`, backed by the same service
layer, with interactive docs at `/api/docs`.

```bash
curl -X POST localhost:8080/api/items \
  -H 'Content-Type: application/json' \
  -d '{"name": "Suitcase", "can_contain_items": true, "tags": ["travel"]}'

curl 'localhost:8080/api/items?q=charger'
curl -X POST localhost:8080/api/scan -H 'Content-Type: application/json' \
  -d '{"code": "01JD..."}'
```

## Data and upgrades

Two named volumes hold everything: `db-data` for PostgreSQL and `photo-data` for
photos. `docker compose down` keeps both; only `down -v` destroys them.

Upgrades preserve data. Migrations are committed to the repository and applied on
container start, before the server binds, so a restart never serves traffic against a
schema it does not understand.

To back up:

```bash
docker compose exec db pg_dump -U objecthub objecthub > objecthub.sql
docker run --rm -v objecthub_photo-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/photos.tar.gz -C /data .
```

## Development

```bash
pip install -r requirements-dev.txt
pytest          # 61 tests, SQLite-backed, no services needed
ruff check .
```

The suite runs on SQLite because the models stick to portable column types; production
runs on PostgreSQL. `make help` lists the other tasks.

### Layout

```text
app/
  models.py        SQLAlchemy models
  schemas.py       API request and response models
  services/        All domain logic: items, locations, tags, labels, photos, search
  api/             JSON API routers
  web/routes.py    Server-rendered UI routes
  templates/       Jinja templates; macros.html holds the components
  static/css/      One design-system stylesheet driven by CSS custom properties
alembic/versions/  Committed migrations
```

Business rules live in `app/services/` and nowhere else — the UI and the API are both
thin layers over it, so behaviour cannot drift between them.

### Changing the look

`app/static/css/app.css` is organised as tokens, then primitives, then components. The
colour, spacing, radius, and shadow scales are CSS custom properties at the top, with
a dark theme that redefines the same names. Adjusting a token restyles the whole
interface; no build step is involved.

## Design decisions

- **No Redis, no workers, no queue.** Nothing in the requirements needs them.
- **Server-rendered HTML with progressive enhancement.** No bundler, no CDN, no
  framework. Every page works with JavaScript disabled.
- **Portable SQL for search.** A household inventory does not justify a search engine.
- **Opaque identifiers, mutable data.** The one rule that keeps printed labels valid
  for the lifetime of the object.

## Not in this version

Multi-user accounts and permissions, native mobile apps, external object storage,
background jobs.

## License

See [LICENSE](LICENSE).
