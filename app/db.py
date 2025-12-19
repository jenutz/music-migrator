"""Tiny SQLite data layer. Single user, no accounts, no migrations."""

import json
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
    created_at TEXT NOT NULL
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
    src_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    dst_service TEXT NOT NULL,
    dst_external_id TEXT,
    dst_title TEXT,
    dst_artists TEXT,
    dst_album TEXT,
    dst_thumbnail TEXT,
    dst_duration_s INTEGER,
    score INTEGER,
    status TEXT NOT NULL DEFAULT 'chosen',
    created_at TEXT NOT NULL,
    UNIQUE (src_track_id, dst_service)
);

CREATE INDEX IF NOT EXISTS idx_matches_status
    ON matches (dst_service, status);

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
        _conn.commit()


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return _conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with _lock:
        return _conn.execute(sql, params).fetchone()


# --- settings -------------------------------------------------------------


def get_setting(key: str, default: str | None = None) -> str | None:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        _conn.commit()


# --- tracks / playlists ---------------------------------------------------


def upsert_track(track: dict) -> int:
    """Insert or update one track, return its local id. Caller commits."""
    _conn.execute(
        """
        INSERT INTO tracks (service, external_id, title, artists, album, thumbnail, duration_s)
        VALUES (:service, :external_id, :title, :artists, :album, :thumbnail, :duration_s)
        ON CONFLICT(service, external_id) DO UPDATE SET
            title = excluded.title,
            artists = excluded.artists,
            album = excluded.album,
            thumbnail = excluded.thumbnail,
            duration_s = excluded.duration_s
        """,
        track,
    )
    row = _conn.execute(
        "SELECT id FROM tracks WHERE service = ? AND external_id = ?",
        (track["service"], track["external_id"]),
    ).fetchone()
    return int(row["id"])


def replace_liked_playlist(service: str, name: str, tracks: list[dict]) -> int:
    """Replace the imported playlist for a service. Returns playlist id."""
    with _lock:
        try:
            _conn.execute(
                "DELETE FROM playlists WHERE service = ? AND name = ?", (service, name)
            )
            cur = _conn.execute(
                "INSERT INTO playlists (service, name, created_at) VALUES (?, ?, ?)",
                (service, name, now()),
            )
            playlist_id = int(cur.lastrowid)
            for position, track in enumerate(tracks):
                track_id = upsert_track(track)
                _conn.execute(
                    "INSERT INTO playlist_tracks (playlist_id, track_id, position) "
                    "VALUES (?, ?, ?)",
                    (playlist_id, track_id, position),
                )
            _conn.commit()
        except Exception:
            _conn.rollback()
            raise
    return playlist_id


def get_liked_playlist(service: str) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM playlists WHERE service = ? ORDER BY id DESC LIMIT 1",
        (service,),
    )


def get_playlist_tracks(playlist_id: int) -> list[sqlite3.Row]:
    return query(
        """
        SELECT t.id, t.service, t.external_id, t.title, t.artists, t.album,
               t.thumbnail, t.duration_s, pt.position
        FROM playlist_tracks pt
        JOIN tracks t ON t.id = pt.track_id
        WHERE pt.playlist_id = ?
        ORDER BY pt.position
        """,
        (playlist_id,),
    )


def get_track(track_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM tracks WHERE id = ?", (track_id,))


# --- matches --------------------------------------------------------------


def save_match(
    src_track_id: int,
    dst_service: str,
    track: dict,
    score: int | None,
    status: str = "chosen",
) -> None:
    with _lock:
        _conn.execute(
            """
            INSERT INTO matches (
                src_track_id, dst_service, dst_external_id, dst_title, dst_artists,
                dst_album, dst_thumbnail, dst_duration_s, score, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(src_track_id, dst_service) DO UPDATE SET
                dst_external_id = excluded.dst_external_id,
                dst_title = excluded.dst_title,
                dst_artists = excluded.dst_artists,
                dst_album = excluded.dst_album,
                dst_thumbnail = excluded.dst_thumbnail,
                dst_duration_s = excluded.dst_duration_s,
                score = excluded.score,
                status = excluded.status,
                created_at = excluded.created_at
            """,
            (
                src_track_id,
                dst_service,
                track.get("external_id"),
                track.get("title"),
                track.get("artists"),
                track.get("album"),
                track.get("thumbnail"),
                track.get("duration_s"),
                score,
                status,
                now(),
            ),
        )
        _conn.commit()


def skip_match(src_track_id: int, dst_service: str) -> None:
    with _lock:
        _conn.execute(
            """
            INSERT INTO matches (src_track_id, dst_service, status, created_at)
            VALUES (?, ?, 'skipped', ?)
            ON CONFLICT(src_track_id, dst_service) DO UPDATE SET
                dst_external_id = NULL,
                status = 'skipped',
                created_at = excluded.created_at
            """,
            (src_track_id, dst_service, now()),
        )
        _conn.commit()


def get_match(src_track_id: int, dst_service: str) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM matches WHERE src_track_id = ? AND dst_service = ?",
        (src_track_id, dst_service),
    )


def match_counts(playlist_id: int, dst_service: str) -> dict[str, int]:
    row = query_one(
        """
        SELECT
            COUNT(pt.id) AS total,
            COALESCE(SUM(CASE WHEN m.status = 'chosen' THEN 1 ELSE 0 END), 0) AS chosen,
            COALESCE(SUM(CASE WHEN m.status = 'applied' THEN 1 ELSE 0 END), 0) AS applied,
            COALESCE(SUM(CASE WHEN m.status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped
        FROM playlist_tracks pt
        LEFT JOIN matches m
            ON m.src_track_id = pt.track_id AND m.dst_service = ?
        WHERE pt.playlist_id = ?
        """,
        (dst_service, playlist_id),
    )
    if not row:
        return {"total": 0, "chosen": 0, "applied": 0, "skipped": 0}
    return {key: int(row[key]) for key in ("total", "chosen", "applied", "skipped")}


def ordered_matches(playlist_id: int, dst_service: str) -> list[sqlite3.Row]:
    return query(
        """
        SELECT pt.position, t.id AS src_track_id, t.title AS src_title,
               t.artists AS src_artists, t.thumbnail AS src_thumbnail,
               t.duration_s AS src_duration_s, t.external_id AS src_external_id,
               m.id AS match_id, m.status, m.score, m.dst_external_id,
               m.dst_title, m.dst_artists, m.dst_album, m.dst_thumbnail
        FROM playlist_tracks pt
        JOIN tracks t ON t.id = pt.track_id
        LEFT JOIN matches m
            ON m.src_track_id = t.id AND m.dst_service = ?
        WHERE pt.playlist_id = ?
        ORDER BY pt.position
        """,
        (dst_service, playlist_id),
    )


def pending_batch(playlist_id: int, dst_service: str, limit: int) -> list[sqlite3.Row]:
    return query(
        """
        SELECT m.id AS match_id, m.dst_external_id, t.title AS src_title,
               t.artists AS src_artists, pt.position
        FROM playlist_tracks pt
        JOIN tracks t ON t.id = pt.track_id
        JOIN matches m ON m.src_track_id = t.id AND m.dst_service = ?
        WHERE pt.playlist_id = ? AND m.status = 'chosen'
        ORDER BY pt.position
        LIMIT ?
        """,
        (dst_service, playlist_id, limit),
    )


def count_pending(playlist_id: int, dst_service: str) -> int:
    row = query_one(
        """
        SELECT COUNT(*) AS c
        FROM playlist_tracks pt
        JOIN matches m ON m.src_track_id = pt.track_id AND m.dst_service = ?
        WHERE pt.playlist_id = ? AND m.status = 'chosen'
        """,
        (dst_service, playlist_id),
    )
    return int(row["c"]) if row else 0


def mark_applied(match_id: int) -> None:
    with _lock:
        _conn.execute("UPDATE matches SET status = 'applied' WHERE id = ?", (match_id,))
        _conn.commit()


def clear_matches(dst_service: str) -> None:
    with _lock:
        _conn.execute("DELETE FROM matches WHERE dst_service = ?", (dst_service,))
        _conn.commit()


# --- search cache ---------------------------------------------------------


def get_cached_search(src_track_id: int, dst_service: str) -> list[dict] | None:
    row = query_one(
        "SELECT payload FROM search_cache WHERE src_track_id = ? AND dst_service = ?",
        (src_track_id, dst_service),
    )
    return json.loads(row["payload"]) if row else None


def set_cached_search(src_track_id: int, dst_service: str, payload: list[dict]) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO search_cache (src_track_id, dst_service, payload, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(src_track_id, dst_service) DO UPDATE SET "
            "payload = excluded.payload, created_at = excluded.created_at",
            (src_track_id, dst_service, json.dumps(payload), now()),
        )
        _conn.commit()


def clear_cached_search(dst_service: str) -> None:
    with _lock:
        _conn.execute("DELETE FROM search_cache WHERE dst_service = ?", (dst_service,))
        _conn.commit()
