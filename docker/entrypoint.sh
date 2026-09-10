#!/bin/sh
# Wait for PostgreSQL, run migrations, then hand over to the server.
#
# Migrations run before the server binds so a rolling restart never serves traffic
# against a schema it does not understand. Existing data is preserved: Alembic only
# applies revisions that have not run yet.

set -eu

echo "[entrypoint] waiting for the database"
python - <<'PY'
import sys
import time

from sqlalchemy import create_engine, text

from app.config import get_settings

url = get_settings().database_url
deadline = time.monotonic() + 60

while True:
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        print("[entrypoint] database is up")
        break
    except Exception as exc:  # noqa: BLE001 - any connection failure is worth retrying
        if time.monotonic() > deadline:
            print(f"[entrypoint] database unreachable after 60s: {exc}", file=sys.stderr)
            raise SystemExit(1)
        time.sleep(1)
PY

echo "[entrypoint] applying migrations"
alembic upgrade head

echo "[entrypoint] starting: $*"
exec "$@"
