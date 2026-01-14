import logging
import re

import ytmusicapi

from .base_music_api import BaseMusicApi

logger = logging.getLogger(__name__)

# Noise words that YouTube titles carry around and Yandex titles usually don't.
_NOISE_PATTERNS = [
    r"\(remastered\s*\d{4}\)",
    r"\(\d{4}\s*remaster\)",
    r"[\(\[](?:digital|remaster(?:ed)?|\d{4}|official|music|video|audio|lyrics?|hd|hq|visuali[sz]er)[^\)\]]*[\)\]]",
]
_NOISE_WORDS = re.compile(
    r"\b(?:official|video|audio|lyrics?|hd|hq|remastered|visuali[sz]er)\b",
    re.IGNORECASE,
)


def strip_tags(title: str) -> str:
    """Remove '(Official Video)', 'Remastered 2011' and friends from a title."""
    result = title or ""
    for pattern in _NOISE_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    result = _NOISE_WORDS.sub("", result)
    return re.sub(r"\s+", " ", result).strip()


class YoutubeClient(BaseMusicApi):
    service = "youtube"

    def __init__(self, token: str | None = None):
        if token:
            auth = ytmusicapi.setup(headers_raw=token, filepath=None)
            self.client = ytmusicapi.YTMusic(auth)
        else:
            self.client = ytmusicapi.YTMusic()

    # --- normalization ---------------------------------------------------

    @staticmethod
    def _biggest_thumbnail(thumbnails) -> str | None:
        if not thumbnails:
            return None
        best = max(thumbnails, key=lambda t: t.get("width") or 0)
        return best.get("url")

    @classmethod
    def _normalize(cls, track: dict, result_type: str | None = None) -> dict:
        album = track.get("album") or {}
        artists = track.get("artists") or []
        duration = track.get("duration_seconds")
        if duration is None:
            duration = (track.get("lengthSeconds") and int(track["lengthSeconds"])) or None
        return {
            "service": "youtube",
            "external_id": track.get("videoId"),
            "title": track.get("title") or "",
            "artists": ", ".join(a.get("name", "") for a in artists) or track.get("author", ""),
            "album": album.get("name") or track.get("album"),
            "thumbnail": cls._biggest_thumbnail(track.get("thumbnails")),
            "duration_s": int(duration) if duration else None,
            "result_type": result_type or track.get("resultType"),
        }

    # --- api -------------------------------------------------------------

    def get_liked_tracks(self) -> list[dict]:
        tracks = self.client.get_liked_songs(limit=10000).get("tracks", [])
        return [self._normalize(t) for t in reversed(tracks)]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        raw = self.client.search(query, filter="songs", limit=limit)
        if not raw:
            # `songs` filter misses some uploads; fall back to a mixed search.
            raw = self.client.search(query, limit=limit)
        results = [r for r in raw if r.get("resultType") in ("song", "video")]
        return [self._normalize(r) for r in results[:limit]]

    def like_tracks(self, track_ids) -> int:
        track_ids = [str(t) for t in track_ids if t]
        for track_id in track_ids:
            self.client.rate_song(track_id, "LIKE")
        return len(track_ids)

    def unlike_tracks(self, track_ids) -> int:
        track_ids = [str(t) for t in track_ids if t]
        for track_id in track_ids:
            self.client.rate_song(track_id, "INDIFFERENT")
        return len(track_ids)

    def create_playlist(self, name: str, track_ids=()) -> str:
        video_ids = [str(t) for t in track_ids if t]
        playlist_id = self.client.create_playlist(name, "", video_ids=video_ids or None)
        if not isinstance(playlist_id, str):
            # ytmusicapi returns an error dict instead of raising on some failures
            raise RuntimeError(f"create_playlist failed: {playlist_id}")
        return playlist_id

    def add_playlist_tracks(self, playlist_id: str, track_ids) -> int:
        video_ids = [str(t) for t in track_ids if t]
        if not video_ids:
            return 0
        self.client.add_playlist_items(playlist_id, videoIds=video_ids, duplicates=False)
        return len(video_ids)
