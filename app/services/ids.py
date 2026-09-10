"""Stable, opaque identifiers.

ULIDs are used everywhere: 26 characters, URL-safe, lexicographically sortable by
creation time, and generated without central coordination. An identifier is assigned
once and never changes, so a label printed today keeps resolving forever.
"""

from ulid import ULID


def new_id() -> str:
    return str(ULID())


def is_valid_id(value: str) -> bool:
    try:
        ULID.from_str(value)
    except (ValueError, TypeError):
        return False
    return True
