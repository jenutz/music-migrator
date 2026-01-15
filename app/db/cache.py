"""Search results kept per (source track, destination service)."""

import json

from .core import _conn, _lock, now, query_one


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
