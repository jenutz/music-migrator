"""Tiny SQLite data layer. Single user, no accounts, no migrations.

Playlists are the unit of work:

* an **imported** playlist holds a snapshot of a service's liked library
  (``source_playlist_id`` is NULL), and
* a **target** playlist is created when you export an imported one; it lives on
  the destination service and its contents are the matches pointing at it.

Target playlists deliberately have no ``playlist_tracks`` rows - their tracks
come from ``matches``, which keeps the source order without duplicating rows.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artists TEXT,
    album TEXT,
    thumbnail TEXT,
    duration_s INTEGER,
    UNIQUE (service, external_id)
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source_playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE,
    -- targets only: 'likes' (like the tracks) or 'playlist' (build a playlist)
    delivery TEXT,
    -- remote playlist id once the destination playlist actually exists
    remote_playlist_id TEXT
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    position INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_playlist_tracks
    ON playlist_tracks (playlist_id, position);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dst_playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    src_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    dst_external_id TEXT,
    dst_title TEXT,
    dst_artists TEXT,
    dst_album TEXT,
    dst_thumbnail TEXT,
    dst_duration_s INTEGER,
    score INTEGER,
    status TEXT NOT NULL DEFAULT 'chosen',
    created_at TEXT NOT NULL,
    UNIQUE (dst_playlist_id, src_track_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_status
    ON matches (dst_playlist_id, status);

CREATE TABLE IF NOT EXISTS search_cache (
    src_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    dst_service TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (src_track_id, dst_service)
);
"""

_lock = threading.RLock()
_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA foreign_keys = ON")
_conn.execute("PRAGMA journal_mode = WAL")
_conn.execute("PRAGMA busy_timeout = 5000")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    with _lock:
        _conn.executescript(SCHEMA)
        _migrate()
        _conn.commit()


def _columns(table: str) -> set[str]:
    return {row["name"] for row in _conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate() -> None:
    """Bring a database from the one-playlist-per-service layout up to date.

    The old schema keyed matches by ``(src_track_id, dst_service)`` and kept a
    single playlist per service, so there was no way to tell which exported
    playlist a match belonged to. Existing matches are parked on a synthetic
    target playlist per destination service.
    """
    tables = {
        row["name"]
        for row in _conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "playlists" not in tables or "matches" not in tables:
        return  # fresh database, SCHEMA already covers it

    if "source_playlist_id" not in _columns("playlists"):
        _conn.execute("ALTER TABLE playlists ADD COLUMN source_playlist_id INTEGER")

    columns = _columns("playlists")
    if "delivery" not in columns:
        _conn.execute("ALTER TABLE playlists ADD COLUMN delivery TEXT")
    if "remote_playlist_id" not in columns:
        _conn.execute("ALTER TABLE playlists ADD COLUMN remote_playlist_id TEXT")

    # every target that existed before this column was created liked its tracks
    _conn.execute(
        "UPDATE playlists SET delivery = 'likes'"
        " WHERE source_playlist_id IS NOT NULL AND delivery IS NULL"
    )

    # The old app had one hard-coded library name; the new one shows "Медиатека".
    _conn.execute(
        "UPDATE playlists SET name = 'Медиатека' WHERE name = 'Liked tracks'"
        " AND source_playlist_id IS NULL"
    )

    if "dst_playlist_id" not in _columns("matches"):
        _rebuild_matches()


def _rebuild_matches() -> None:
    _conn.execute("ALTER TABLE matches RENAME TO matches_legacy")
    # The old index follows the renamed table, so drop it or the CREATE INDEX
    # in SCHEMA is skipped and the new table ends up unindexed.
    _conn.execute("DROP INDEX IF EXISTS idx_matches_status")
    _conn.executescript(SCHEMA)

    services = [
        row["dst_service"]
        for row in _conn.execute("SELECT DISTINCT dst_service FROM matches_legacy").fetchall()
    ]

    for dst_service in services:
        source = _conn.execute(
            "SELECT id FROM playlists WHERE service != ? ORDER BY id DESC LIMIT 1",
            (dst_service,),
        ).fetchone()
        if not source:
            continue

        cur = _conn.execute(
            "INSERT INTO playlists (service, name, created_at, source_playlist_id) "
            "VALUES (?, ?, ?, ?)",
            (dst_service, "перенос", now(), source["id"]),
        )
        _conn.execute(
            """
            INSERT INTO matches (
                dst_playlist_id, src_track_id, dst_external_id, dst_title, dst_artists,
                dst_album, dst_thumbnail, dst_duration_s, score, status, created_at
            )
            SELECT ?, src_track_id, dst_external_id, dst_title, dst_artists,
                   dst_album, dst_thumbnail, dst_duration_s, score, status, created_at
            FROM matches_legacy WHERE dst_service = ?
            """,
            (cur.lastrowid, dst_service),
        )

    _conn.execute("DROP TABLE matches_legacy")


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return _conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with _lock:
        return _conn.execute(sql, params).fetchone()
