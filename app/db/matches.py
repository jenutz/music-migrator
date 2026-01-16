"""``src_playlist_id`` is the imported playlist, ``dst_playlist_id`` is the
target created by exporting it. Every function takes both so nothing has to
guess which playlist a match belongs to.
"""

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from .core import now, session
from .models import Match, PlaylistTrack, Track

_RANKED_STATUSES = ("chosen", "applied", "skipped")


def _match_row(db_session: Session, dst_playlist_id: int, src_track_id: int) -> Match | None:
    return db_session.scalar(
        select(Match).where(
            Match.dst_playlist_id == dst_playlist_id,
            Match.src_track_id == src_track_id,
        )
    )


def save_match(
    dst_playlist_id: int,
    src_track_id: int,
    track: dict,
    score: int | None,
    status: str = "chosen",
) -> None:
    with session() as db_session:
        match = _match_row(db_session, dst_playlist_id, src_track_id)
        if match is None:
            match = Match(dst_playlist_id=dst_playlist_id, src_track_id=src_track_id)
            db_session.add(match)

        match.dst_external_id = track.get("external_id")
        match.dst_title = track.get("title")
        match.dst_artists = track.get("artists")
        match.dst_album = track.get("album")
        match.dst_thumbnail = track.get("thumbnail")
        match.dst_duration_s = track.get("duration_s")
        match.score = score
        match.status = status
        match.created_at = now()


def skip_match(dst_playlist_id: int, src_track_id: int) -> None:
    with session() as db_session:
        match = _match_row(db_session, dst_playlist_id, src_track_id)
        if match is None:
            match = Match(dst_playlist_id=dst_playlist_id, src_track_id=src_track_id)
            db_session.add(match)

        match.dst_external_id = None
        match.status = "skipped"
        match.created_at = now()


def get_match(dst_playlist_id: int, src_track_id: int) -> Match | None:
    with session() as db_session:
        return _match_row(db_session, dst_playlist_id, src_track_id)


def match_counts(src_playlist_id: int, dst_playlist_id: int) -> dict[str, int]:
    with session() as db_session:
        total = db_session.scalar(
            select(func.count())
            .select_from(PlaylistTrack)
            .where(PlaylistTrack.playlist_id == src_playlist_id)
        )
        rows = db_session.execute(
            select(Match.status, func.count())
            .join(
                PlaylistTrack,
                and_(
                    PlaylistTrack.track_id == Match.src_track_id,
                    PlaylistTrack.playlist_id == src_playlist_id,
                ),
            )
            .where(Match.dst_playlist_id == dst_playlist_id)
            .group_by(Match.status)
        ).all()

    counts = {"total": int(total or 0), "chosen": 0, "applied": 0, "skipped": 0}
    for status, count in rows:
        if status in _RANKED_STATUSES:
            counts[status] = int(count)
    return counts


def ordered_matches(src_playlist_id: int, dst_playlist_id: int) -> list[dict]:
    with session() as db_session:
        rows = db_session.execute(
            select(
                PlaylistTrack.position,
                Track.id.label("src_track_id"),
                Track.title.label("src_title"),
                Track.artists.label("src_artists"),
                Track.thumbnail.label("src_thumbnail"),
                Track.duration_s.label("src_duration_s"),
                Track.external_id.label("src_external_id"),
                Match.id.label("match_id"),
                Match.status,
                Match.score,
                Match.dst_external_id,
                Match.dst_title,
                Match.dst_artists,
                Match.dst_album,
                Match.dst_thumbnail,
            )
            .select_from(PlaylistTrack)
            .join(Track, Track.id == PlaylistTrack.track_id)
            .outerjoin(
                Match,
                and_(
                    Match.src_track_id == Track.id,
                    Match.dst_playlist_id == dst_playlist_id,
                ),
            )
            .where(PlaylistTrack.playlist_id == src_playlist_id)
            .order_by(PlaylistTrack.position)
        )
        return [dict(row._mapping) for row in rows]


def pending_batch(src_playlist_id: int, dst_playlist_id: int, limit: int) -> list[dict]:
    with session() as db_session:
        rows = db_session.execute(
            select(
                Match.id.label("match_id"),
                Match.dst_external_id,
                Track.title.label("src_title"),
                Track.artists.label("src_artists"),
                PlaylistTrack.position,
            )
            .select_from(PlaylistTrack)
            .join(Track, Track.id == PlaylistTrack.track_id)
            .join(
                Match,
                and_(
                    Match.src_track_id == Track.id,
                    Match.dst_playlist_id == dst_playlist_id,
                ),
            )
            .where(
                PlaylistTrack.playlist_id == src_playlist_id,
                Match.status == "chosen",
            )
            .order_by(PlaylistTrack.position)
            .limit(limit)
        )
        return [dict(row._mapping) for row in rows]


def count_pending(src_playlist_id: int, dst_playlist_id: int) -> int:
    with session() as db_session:
        return int(
            db_session.scalar(
                select(func.count())
                .select_from(PlaylistTrack)
                .join(
                    Match,
                    and_(
                        Match.src_track_id == PlaylistTrack.track_id,
                        Match.dst_playlist_id == dst_playlist_id,
                    ),
                )
                .where(
                    PlaylistTrack.playlist_id == src_playlist_id,
                    Match.status == "chosen",
                )
            )
            or 0
        )


def mark_applied(match_id: int) -> None:
    with session() as db_session:
        match = db_session.get(Match, match_id)
        if match:
            match.status = "applied"


def clear_matches(dst_playlist_id: int) -> None:
    with session() as db_session:
        db_session.execute(delete(Match).where(Match.dst_playlist_id == dst_playlist_id))
