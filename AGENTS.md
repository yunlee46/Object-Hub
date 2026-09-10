# AGENTS.md

## Project

Build a self-hosted physical inventory application for tracking real-world objects,
containers, locations, labels, photos, tags, and movement history.

The application must be deployable on a NAS using Docker Compose.

## Core principles

- Prefer simple, maintainable solutions over unnecessary complexity.
- The application must work without external cloud services.
- All object identifiers must remain stable for the lifetime of the object.
- Never encode mutable information such as names or locations into QR codes.
- Preserve existing user data during migrations and upgrades.
- Do not introduce a service unless it is justified by a concrete requirement.

## Recommended architecture

Use a modular web application with:

- PostgreSQL for relational data
- Local persistent storage for uploaded photos
- Docker Compose for production deployment
- Database migrations committed to the repository
- Responsive browser UI suitable for mobile phone scanning

Redis is not required for the initial version.

## Main concepts

### Item

An item is any tracked physical object.

Examples:

- Charger
- Book
- Camera
- Battery
- Storage cabinet
- Suitcase

Items may optionally contain other items.

### Container

A container is an item that can contain other items.

Examples:

- Room
- Cabinet
- Shelf
- Suitcase
- Storage box
- Vehicle

Do not create a separate database entity for containers unless there is a clear
requirement. Prefer an item with `can_contain_items = true`.

### Location

A location is a physical place where an item currently exists.

Examples:

- House
- Garage
- Office
- Storage room
- Vehicle

Locations may also be hierarchical.

### Label

A label identifies one specific item and must contain an opaque, permanent identifier.

Supported label types:

- QR code
- Data Matrix code
- Code 128 barcode
- Existing manufacturer barcode

The initial implementation should prioritize QR codes and existing barcode scanning.

## Required functionality

### Item management

Users must be able to:

- Create, edit, archive, and restore items
- Assign an item to a parent container
- Assign an item to a physical location
- Add a description and notes
- Add one or more photos
- Add arbitrary tags
- Mark whether the item can contain other items
- View the complete containment path

### Hierarchy

Items can be nested:

```text
Garage
└── Cabinet A
    └── Tool Box
        └── Screwdriver
```

Hierarchy rules:

- An item may have at most one parent item.
- A parent must have `can_contain_items = true`.
- Cycles are forbidden; an item may never be its own ancestor.
- Moving a container moves its entire subtree implicitly.
- An item's effective location is inherited from its nearest ancestor that has an
  explicit location, unless the item sets its own.

### Locations

- Locations form their own hierarchy, independent of item containment.
- An explicit location may be set on any item, not only on containers.
- Deleting a location must not delete items; it detaches them instead.

### Labels and identifiers

- Every item receives an opaque, permanent, URL-safe identifier at creation.
- Identifiers are ULIDs: sortable by creation time, collision-resistant, no
  central coordination required.
- A QR code encodes only a resolver path containing that identifier.
- An item may have multiple labels, including pre-existing manufacturer barcodes.
- Scanning an unknown code offers to register it against an existing item.
- Labels are printable as a paginated sheet sized for common sticker stock.

### Photos

- Photos are stored on a local volume, never in the database.
- Stored files are named by a generated identifier, never by the upload filename.
- Uploads are validated by decoding the image, not by trusting the content type.
- A downscaled thumbnail is generated on upload for list views.
- One photo per item may be marked primary.

### Search

Users must be able to find items by name, description, notes, tag, location, and
label code, and to filter by archived state and container capability.

### Movement history

- Every change of parent or location is recorded as an immutable movement row.
- History records the previous and next value, a timestamp, and an optional note.
- History is never rewritten, only appended.

### API

- A JSON API under `/api` backs every operation the UI performs.
- The server-rendered UI and the API share the same service layer.

## Deployment

- One Compose stack: application container plus PostgreSQL.
- Photos and database data live on named volumes.
- Migrations run automatically on container start before the server binds.
- Configuration comes from environment variables with safe defaults.

## Non-goals for the initial version

- Multi-tenancy and per-user permissions
- Redis, background workers, and message queues
- Native mobile applications
- External object storage
