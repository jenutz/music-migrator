from sqlalchemy import func, select

from .core import now, session
from .matches import match_counts
from .models import Playlist, PlaylistTrack
from .tracks import _upsert


def create_playlist(
    service: str,
    name: str,
    tracks: list[dict] | None = None,
    source_playlist_id: int | None = None,
    delivery: str | None = None,
) -> int:
    with session() as db_session:
        playlist = Playlist(
            service=service,
            name=name,
            created_at=now(),
            source_playlist_id=source_playlist_id,
            delivery=delivery,
        )
        db_session.add(playlist)
        db_session.flush()

        for position, track in enumerate(tracks or []):
            db_session.add(
                PlaylistTrack(
                    playlist_id=playlist.id,
                    track_id=_upsert(db_session, track).id,
                    position=position,
                )
            )

        db_session.flush()
        return playlist.id


def get_playlist(playlist_id: int) -> Playlist | None:
    with session() as db_session:
        return db_session.get(Playlist, playlist_id)


def delete_playlist(playlist_id: int) -> None:
    """Drop the playlist; SQLite cascades to its entries, matches and exports."""
    with session() as db_session:
        playlist = db_session.get(Playlist, playlist_id)
        if playlist:
            db_session.delete(playlist)


def list_playlists(service: str | None = None) -> list[Playlist]:
    statement = select(Playlist).order_by(Playlist.created_at.desc(), Playlist.id.desc())
    if service:
        statement = statement.where(Playlist.service == service)
    with session() as db_session:
        return list(db_session.scalars(statement))


def set_remote_playlist(playlist_id: int, remote_id: str) -> None:
    with session() as db_session:
        playlist = db_session.get(Playlist, playlist_id)
        if playlist:
            playlist.remote_playlist_id = remote_id


def playlist_kind(playlist: Playlist) -> str:
    return playlist.kind


def playlist_track_count(playlist_id: int) -> int:
    with session() as db_session:
        return int(
            db_session.scalar(
                select(func.count())
                .select_from(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
            )
            or 0
        )


def playlist_counts(playlist: Playlist) -> dict[str, int]:
    if playlist.source_playlist_id:
        return match_counts(playlist.source_playlist_id, playlist.id)
    return {
        "total": playlist_track_count(playlist.id),
        "chosen": 0,
        "applied": 0,
        "skipped": 0,
    }


def playlist_tracks(playlist_id: int) -> list[PlaylistTrack]:
    with session() as db_session:
        return list(
            db_session.scalars(
                select(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .order_by(PlaylistTrack.position)
            )
        )
