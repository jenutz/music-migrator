"""The catalogue of every track we have ever seen, per service."""

import sqlite3

from .core import _conn, query, query_one


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


def get_track(track_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM tracks WHERE id = ?", (track_id,))


def tracks_for_service(service: str) -> list[sqlite3.Row]:
    return query(
        """
        SELECT service, external_id, title, artists, album, thumbnail, duration_s
        FROM tracks
        WHERE service = ?
        """,
        (service,),
    )
