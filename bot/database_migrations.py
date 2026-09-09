"""SQLite schema versioning and fail-safe migrations for ALIMJ.

The bot intentionally keeps migrations small and dependency-free. Existing
pre-V36 databases are adopted as the current baseline after their normal
schema initialization has completed. Future schema changes can then be added
as numbered, idempotent migrations without changing callers of bot.database.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from bot.logger import logger

SCHEMA_VERSION = 1
MIGRATION_LOCK_RETRIES = 4
MIGRATION_LOCK_BACKOFF = 0.08


@dataclass(frozen=True)
class Migration:
    version: int
    name: str


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "baseline_v36_schema_tracking"),
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _create_tracking_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )


def _read_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()
    if not row:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        raise RuntimeError("Invalid database schema_version metadata")


def _write_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES('schema_version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(version),),
    )


def _apply_baseline(conn: sqlite3.Connection) -> None:
    """Adopt a pre-V36 database without altering user data."""
    # init_db has already created/altered the operational schema. This
    # migration only introduces tracking metadata, so it is data-safe.
    _write_version(conn, 1)
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) "
        "VALUES(1,?,datetime('now'))",
        (MIGRATIONS[0].name,),
    )


def _backup_before_migration(conn: sqlite3.Connection, db_path: str | Path) -> Path:
    """Create a SQLite backup beside the DB before a non-baseline migration."""
    source = Path(db_path)
    backup = source.with_name(f"{source.stem}.pre_migration_v{SCHEMA_VERSION}.db")
    tmp = backup.with_suffix(backup.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    dst = sqlite3.connect(str(tmp))
    try:
        conn.backup(dst)
        dst.commit()
    finally:
        dst.close()
    tmp.replace(backup)
    return backup


def ensure_schema_version(conn: sqlite3.Connection, db_path: str | Path | None = None) -> int:
    """Ensure schema tracking exists and all known migrations are applied.

    Returns the resulting schema version. A malformed/future version fails
    closed rather than silently changing an unknown database.
    """
    _create_tracking_tables(conn)
    current = _read_version(conn)
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current} is newer than supported {SCHEMA_VERSION}"
        )

    if current == SCHEMA_VERSION:
        conn.commit()
        return current

    # Version 0 is the pre-V36 database. Tracking metadata itself is the
    # baseline migration and does not require a destructive transformation.
    if current == 0:
        # Even the metadata-only baseline is a migration boundary. If this is
        # an existing operational DB, snapshot it before writing tracking data.
        if db_path and _table_exists(conn, "users"):
            try:
                backup = _backup_before_migration(conn, db_path)
                logger.info("Pre-migration DB backup created: %s", backup.name)
            except Exception as exc:
                raise RuntimeError(f"Pre-migration database backup failed: {exc}") from exc
        _apply_baseline(conn)
        conn.commit()
        logger.info("Database schema baseline registered at V1")
        return 1

    # Future numbered migrations belong here. Keep the guard so an accidental
    # gap never advances schema metadata without a real migration.
    for migration in MIGRATIONS:
        if current < migration.version:
            raise RuntimeError(f"Missing migration implementation for V{migration.version}")

    conn.commit()
    return current


def schema_status(conn: sqlite3.Connection) -> dict[str, object]:
    """Return safe schema metadata for diagnostics/tests."""
    _create_tracking_tables(conn)
    version = _read_version(conn)
    rows = conn.execute(
        "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {
        "version": version,
        "supported_version": SCHEMA_VERSION,
        "migrations": [
            {"version": int(v), "name": name, "applied_at": applied}
            for v, name, applied in rows
        ],
    }
