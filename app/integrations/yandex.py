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

    # --- normalization ---------------------------------------------------

    @staticmethod
    def _cover(album) -> str | None:
        """Albums occasionally come back without a cover, and the library
        asserts on that instead of returning None."""
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

    # --- api -------------------------------------------------------------

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
