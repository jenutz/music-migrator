"""Imported snapshots and the targets exported from them."""

import sqlite3

from .core import _conn, _lock, now, query, query_one
from .matches import match_counts
from .tracks import upsert_track


def create_playlist(
    service: str,
    name: str,
    tracks: list[dict] | None = None,
    source_playlist_id: int | None = None,
    delivery: str | None = None,
) -> int:
    """Create a playlist, optionally seeded with tracks (imported playlists)."""
    with _lock:
        try:
            cur = _conn.execute(
                "INSERT INTO playlists "
                "(service, name, created_at, source_playlist_id, delivery) "
                "VALUES (?, ?, ?, ?, ?)",
                (service, name, now(), source_playlist_id, delivery),
            )
            playlist_id = int(cur.lastrowid)

            for position, track in enumerate(tracks or []):
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


def get_playlist(playlist_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM playlists WHERE id = ?", (playlist_id,))


def delete_playlist(playlist_id: int) -> None:
    with _lock:
        _conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        _conn.commit()


def list_playlists(service: str | None = None) -> list[sqlite3.Row]:
    if service:
        return query(
            "SELECT * FROM playlists WHERE service = ? ORDER BY created_at DESC, id DESC",
            (service,),
        )
    return query("SELECT * FROM playlists ORDER BY created_at DESC, id DESC")


def set_remote_playlist(playlist_id: int, remote_id: str) -> None:
    with _lock:
        _conn.execute(
            "UPDATE playlists SET remote_playlist_id = ? WHERE id = ?",
            (remote_id, playlist_id),
        )
        _conn.commit()


def playlist_kind(playlist: sqlite3.Row) -> str:
    return "target" if playlist["source_playlist_id"] else "imported"


def playlist_track_count(playlist_id: int) -> int:
    row = query_one(
        "SELECT COUNT(*) AS c FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
    )
    return int(row["c"]) if row else 0


def playlist_counts(playlist: sqlite3.Row) -> dict[str, int]:
    """Counts for a playlist of either kind."""
    if playlist["source_playlist_id"]:
        return match_counts(playlist["source_playlist_id"], playlist["id"])
    return {
        "total": playlist_track_count(playlist["id"]),
        "chosen": 0,
        "applied": 0,
        "skipped": 0,
    }


def playlist_tracks(playlist_id: int) -> list[sqlite3.Row]:
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
