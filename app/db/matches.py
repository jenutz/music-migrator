"""Matches: what a source track became on the destination.

``src_playlist_id`` is the imported playlist, ``dst_playlist_id`` is the target
created by exporting it. Every function takes both so nothing has to guess
which playlist a match belongs to.
"""

import sqlite3

from .core import _conn, _lock, now, query, query_one


def save_match(
    dst_playlist_id: int,
    src_track_id: int,
    track: dict,
    score: int | None,
    status: str = "chosen",
) -> None:
    with _lock:
        _conn.execute(
            """
            INSERT INTO matches (
                dst_playlist_id, src_track_id, dst_external_id, dst_title, dst_artists,
                dst_album, dst_thumbnail, dst_duration_s, score, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dst_playlist_id, src_track_id) DO UPDATE SET
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
                dst_playlist_id,
                src_track_id,
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


def skip_match(dst_playlist_id: int, src_track_id: int) -> None:
    with _lock:
        _conn.execute(
            """
            INSERT INTO matches (dst_playlist_id, src_track_id, status, created_at)
            VALUES (?, ?, 'skipped', ?)
            ON CONFLICT(dst_playlist_id, src_track_id) DO UPDATE SET
                dst_external_id = NULL,
                status = 'skipped',
                created_at = excluded.created_at
            """,
            (dst_playlist_id, src_track_id, now()),
        )
        _conn.commit()


def get_match(dst_playlist_id: int, src_track_id: int) -> sqlite3.Row | None:
    return query_one(
        "SELECT * FROM matches WHERE dst_playlist_id = ? AND src_track_id = ?",
        (dst_playlist_id, src_track_id),
    )


def match_counts(src_playlist_id: int, dst_playlist_id: int) -> dict[str, int]:
    row = query_one(
        """
        SELECT
            COUNT(pt.id) AS total,
            COALESCE(SUM(CASE WHEN m.status = 'chosen' THEN 1 ELSE 0 END), 0) AS chosen,
            COALESCE(SUM(CASE WHEN m.status = 'applied' THEN 1 ELSE 0 END), 0) AS applied,
            COALESCE(SUM(CASE WHEN m.status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped
        FROM playlist_tracks pt
        LEFT JOIN matches m
            ON m.src_track_id = pt.track_id AND m.dst_playlist_id = ?
        WHERE pt.playlist_id = ?
        """,
        (dst_playlist_id, src_playlist_id),
    )
    if not row:
        return {"total": 0, "chosen": 0, "applied": 0, "skipped": 0}
    return {key: int(row[key]) for key in ("total", "chosen", "applied", "skipped")}


def ordered_matches(src_playlist_id: int, dst_playlist_id: int) -> list[sqlite3.Row]:
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
            ON m.src_track_id = t.id AND m.dst_playlist_id = ?
        WHERE pt.playlist_id = ?
        ORDER BY pt.position
        """,
        (dst_playlist_id, src_playlist_id),
    )


def pending_batch(src_playlist_id: int, dst_playlist_id: int, limit: int) -> list[sqlite3.Row]:
    return query(
        """
        SELECT m.id AS match_id, m.dst_external_id, t.title AS src_title,
               t.artists AS src_artists, pt.position
        FROM playlist_tracks pt
        JOIN tracks t ON t.id = pt.track_id
        JOIN matches m ON m.src_track_id = t.id AND m.dst_playlist_id = ?
        WHERE pt.playlist_id = ? AND m.status = 'chosen'
        ORDER BY pt.position
        LIMIT ?
        """,
        (dst_playlist_id, src_playlist_id, limit),
    )


def count_pending(src_playlist_id: int, dst_playlist_id: int) -> int:
    row = query_one(
        """
        SELECT COUNT(*) AS c
        FROM playlist_tracks pt
        JOIN matches m ON m.src_track_id = pt.track_id AND m.dst_playlist_id = ?
        WHERE pt.playlist_id = ? AND m.status = 'chosen'
        """,
        (dst_playlist_id, src_playlist_id),
    )
    return int(row["c"]) if row else 0


def mark_applied(match_id: int) -> None:
    with _lock:
        _conn.execute("UPDATE matches SET status = 'applied' WHERE id = ?", (match_id,))
        _conn.commit()


def clear_matches(dst_playlist_id: int) -> None:
    with _lock:
        _conn.execute("DELETE FROM matches WHERE dst_playlist_id = ?", (dst_playlist_id,))
        _conn.commit()
