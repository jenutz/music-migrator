"""Fetch a service's liked library and persist it locally."""

import logging

from app import db
from app.integrations.factory import choose_api

logger = logging.getLogger(__name__)

LIBRARY_NAME = "Liked tracks"

# Keys the integrations may emit that we don't store.
_TRACK_KEYS = ("service", "external_id", "title", "artists", "album", "thumbnail", "duration_s")


class ImportService:
    """Imports the liked library of one service into the local database."""

    def __init__(self, service: str):
        self.service = service

    def _clean(self, track: dict) -> dict:
        cleaned = {key: track.get(key) for key in _TRACK_KEYS}
        cleaned["service"] = self.service
        cleaned["external_id"] = str(cleaned["external_id"])
        cleaned["title"] = cleaned["title"] or ""
        return cleaned

    def run(self) -> dict:
        token = db.get_setting(f"token-{self.service}")
        if not token:
            raise ValueError(f"No token stored for {self.service}")

        client = choose_api(self.service, token)
        logger.info("Fetching liked tracks from %s", self.service)
        raw = client.get_liked_tracks()

        tracks = []
        skipped = 0
        for track in raw:
            if not track.get("external_id"):
                continue
            try:
                tracks.append(self._clean(track))
            except Exception:  # one weird track should not sink the import
                skipped += 1
                logger.warning("Skipping unparsable %s track: %r", self.service, track)

        playlist_id = db.replace_liked_playlist(self.service, LIBRARY_NAME, tracks)
        logger.info("Stored %s tracks for %s (%s skipped)", len(tracks), self.service, skipped)

        return {
            "service": self.service,
            "playlist_id": playlist_id,
            "imported": len(tracks),
            "skipped": skipped,
        }

    @staticmethod
    def status(service: str) -> dict:
        playlist = db.get_liked_playlist(service)
        return {
            "service": service,
            "has_token": bool(db.get_setting(f"token-{service}")),
            "playlist_id": playlist["id"] if playlist else None,
            "imported": len(db.get_playlist_tracks(playlist["id"])) if playlist else 0,
        }
