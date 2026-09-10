"""Test fixtures.

The suite runs against SQLite so it needs no services, which is only possible because
the models stick to portable column types. Photos are written to a temporary directory
that is discarded with the session.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Configured before importing the application, because the engine and the storage
# paths are resolved at import time.
_TMP = Path(tempfile.mkdtemp(prefix="objecthub-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["APP_NAME"] = "Object Hub Test"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_schema() -> Iterator[None]:
    """A fresh schema per test, so ordering never matters."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def png_bytes() -> bytes:
    """A real, decodable PNG, since uploads are validated by decoding."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (60, 40), (90, 120, 220)).save(buffer, format="PNG")
    return buffer.getvalue()
