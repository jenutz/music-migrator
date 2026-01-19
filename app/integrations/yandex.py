import logging

import yandex_music

from .base_music_api import BaseMusicApi

logger = logging.getLogger(__name__)


class YandexClient(BaseMusicApi):
    service = "yandex"

    def __init__(self, token: str | None = None):
        if token:
            self.client = yandex_music.Client(token).init()
        else:
            self.client = yandex_music.Client().init()

    @staticmethod
    def _cover(album) -> str | None:
        cover_uri = getattr(album, "cover_uri", None)
        if not isinstance(cover_uri, str):
            return None
        try:
            return album.get_cover_url("200x200")
        except (AssertionError, ValueError):
            return None

    @classmethod
    def _normalize(cls, track: "yandex_music.Track") -> dict:
        album = track.albums[0] if track.albums else None
        return {
            "service": "yandex",
            "external_id": str(track.id),
            "title": track.title or "",
            "artists": ", ".join(a.name for a in track.artists or []),
            "album": getattr(album, "title", None),
            "thumbnail": cls._cover(album) if album else None,
            "duration_s": track.duration_ms // 1000 if track.duration_ms else None,
        }

    def get_liked_tracks(self) -> list[dict]:
        tracks = self.client.users_likes_tracks().fetch_tracks() or []
        return [self._normalize(t) for t in reversed(tracks)]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        result = self.client.search(query, type_="track")
        tracks = getattr(getattr(result, "tracks", None), "results", None) or []
        return [self._normalize(t) for t in tracks[:limit]]

    def like_tracks(self, track_ids) -> int:
        track_ids = [str(t) for t in track_ids]
        if not track_ids:
            return 0
        self.client.users_likes_tracks_add(track_ids)
        return len(track_ids)

    def unlike_tracks(self, track_ids) -> int:
        track_ids = [str(t) for t in track_ids]
        if not track_ids:
            return 0
        self.client.users_likes_tracks_remove(track_ids)
        return len(track_ids)

    def _album_ids(self, track_ids: list[str]) -> dict[str, str]:
        found = {}
        try:
            tracks = self.client.tracks(track_ids) or []
        except Exception:
            logger.exception("Could not resolve album ids for %s tracks", len(track_ids))
            return found

        for track in tracks:
            album = track.albums[0] if track.albums else None
            if album is not None:
                found[str(track.id)] = str(album.id)
        return found

    def create_playlist(self, name: str, track_ids=()) -> str:
        playlist = self.client.users_playlists_create(name, visibility="private")
        if playlist is None or playlist.kind is None:
            raise RuntimeError("users_playlists_create returned nothing")
        playlist_id = str(playlist.kind)
        if track_ids:
            self.add_playlist_tracks(playlist_id, track_ids)
        return playlist_id

    def add_playlist_tracks(self, playlist_id: str, track_ids) -> int:
        track_ids = [str(t) for t in track_ids if t]
        if not track_ids:
            return 0

        playlist = self.client.users_playlists(playlist_id)
        at = int(getattr(playlist, "track_count", 0) or 0)
        albums = self._album_ids(track_ids)

        sent = 0
        for track_id in track_ids:
            album_id = albums.get(track_id)
            if not album_id:
                logger.warning("Skipping %s: no album id, cannot insert", track_id)
                continue
            self.client.users_playlists_insert_track(playlist_id, track_id, album_id, at=at)
            at += 1
            sent += 1
        return sent
