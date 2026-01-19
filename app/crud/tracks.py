from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import session
from app.models import Track


def _upsert(db_session: Session, track: dict) -> Track:
    service = track["service"]
    external_id = str(track["external_id"])

    row = db_session.scalar(
        select(Track).where(Track.service == service, Track.external_id == external_id)
    )
    if row is None:
        row = Track(service=service, external_id=external_id)
        db_session.add(row)

    row.title = track.get("title") or ""
    row.artists = track.get("artists")
    row.album = track.get("album")
    row.thumbnail = track.get("thumbnail")
    row.duration_s = track.get("duration_s")
    db_session.flush()
    return row


def upsert_track(track: dict) -> int:
    with session() as db_session:
        return _upsert(db_session, track).id


def get_track(track_id: int) -> Track | None:
    with session() as db_session:
        return db_session.get(Track, track_id)


def tracks_for_service(service: str) -> list[Track]:
    with session() as db_session:
        return list(db_session.scalars(select(Track).where(Track.service == service)))
