"""Check that the configured database matches the application models.

The default check is read-only. Use ``--write-probe`` to perform a temporary
insert/read check that is always rolled back.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.config import get_settings
from app.database import Base, ChatRepository


def safe_target(database_url: str) -> dict[str, str]:
    """Return database identity without credentials or connection options."""
    url = make_url(database_url)
    return {
        "driver": url.drivername,
        "host": url.host or "local",
        "database": url.database or "",
    }


def schema_issues(repository: ChatRepository) -> list[dict[str, Any]]:
    """Compare tables, columns, foreign keys, and named indexes."""
    database_inspector = inspect(repository.engine)
    live_tables = set(database_inspector.get_table_names())
    expected_tables = set(Base.metadata.tables)
    issues: list[dict[str, Any]] = []

    if missing := sorted(expected_tables - live_tables):
        issues.append({"kind": "missing_tables", "items": missing})
    if unexpected := sorted(live_tables - expected_tables):
        issues.append({"kind": "unexpected_tables", "items": unexpected})

    for table_name in sorted(expected_tables & live_tables):
        table = Base.metadata.tables[table_name]
        expected_columns = set(table.columns.keys())
        live_columns = {
            column["name"] for column in database_inspector.get_columns(table_name)
        }
        if missing := sorted(expected_columns - live_columns):
            issues.append(
                {"kind": "missing_columns", "table": table_name, "items": missing}
            )
        if unexpected := sorted(live_columns - expected_columns):
            issues.append(
                {
                    "kind": "unexpected_columns",
                    "table": table_name,
                    "items": unexpected,
                }
            )

        expected_foreign_keys = len(table.foreign_key_constraints)
        live_foreign_keys = len(database_inspector.get_foreign_keys(table_name))
        if expected_foreign_keys != live_foreign_keys:
            issues.append(
                {
                    "kind": "foreign_key_count",
                    "table": table_name,
                    "expected": expected_foreign_keys,
                    "actual": live_foreign_keys,
                }
            )

        expected_indexes = {index.name for index in table.indexes if index.name}
        live_indexes = {
            index["name"]
            for index in database_inspector.get_indexes(table_name)
            if index.get("name")
        }
        if missing := sorted(expected_indexes - live_indexes):
            issues.append(
                {"kind": "missing_indexes", "table": table_name, "items": missing}
            )

    return issues


def rollback_write_probe(repository: ChatRepository) -> bool:
    """Verify insert and read behavior without retaining the probe record."""
    probe_id = str(uuid.uuid4())
    probe_wa_id = f"999{probe_id.replace('-', '')[:9]}"

    with repository.engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                text(
                    "INSERT INTO contacts "
                    "(id, wa_id, display_name, created_at, updated_at) "
                    "VALUES (:id, :wa_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": probe_id,
                    "wa_id": probe_wa_id,
                    "display_name": "database sync probe",
                },
            )
            stored_name = connection.execute(
                text("SELECT display_name FROM contacts WHERE id = :id"),
                {"id": probe_id},
            ).scalar_one()
            return stored_name == "database sync probe"
        finally:
            transaction.rollback()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-probe",
        action="store_true",
        help="run a rollback-only insert and read check",
    )
    args = parser.parse_args()

    settings = get_settings()
    repository = ChatRepository(
        settings.DATABASE_URL,
        settings.SESSION_TTL_SECONDS,
    )
    connected = repository.ping()
    result: dict[str, Any] = {
        "target": safe_target(settings.DATABASE_URL),
        "connected": connected,
        "schema_synced": False,
        "issues": [],
    }

    if connected:
        result["issues"] = schema_issues(repository)
        result["schema_synced"] = not result["issues"]
        if args.write_probe:
            result["rollback_write_probe"] = rollback_write_probe(repository)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if connected and result["schema_synced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
