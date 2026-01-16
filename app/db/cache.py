import json

from sqlalchemy import delete, select

from .core import now, session
from .models import SearchCache


def get_cached_search(src_track_id: int, dst_service: str) -> list[dict] | None:
    with session() as db_session:
        row = db_session.scalar(
            select(SearchCache).where(
                SearchCache.src_track_id == src_track_id,
                SearchCache.dst_service == dst_service,
            )
        )
        return json.loads(row.payload) if row else None


def set_cached_search(src_track_id: int, dst_service: str, payload: list[dict]) -> None:
    with session() as db_session:
        row = db_session.get(SearchCache, (src_track_id, dst_service))
        if row is None:
            row = SearchCache(src_track_id=src_track_id, dst_service=dst_service)
            db_session.add(row)
        row.payload = json.dumps(payload)
        row.created_at = now()


def clear_cached_search(dst_service: str) -> None:
    with session() as db_session:
        db_session.execute(delete(SearchCache).where(SearchCache.dst_service == dst_service))
