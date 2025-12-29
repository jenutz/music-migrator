"""Push the chosen matches of one target playlist to the destination service."""

import logging

from app import db
from app.integrations.factory import choose_api

logger = logging.getLogger(__name__)

# Services rate-limit aggressively; keep batches small and resumable.
BATCH_SIZE = 50


class ApplyService:
    """Likes every chosen track of a target playlist, in source playlist order."""

    def __init__(self, dst_playlist_id: int):
        playlist = db.get_playlist(dst_playlist_id)
        if not playlist:
            raise ValueError(f"Unknown playlist {dst_playlist_id}")
        if not playlist["source_playlist_id"]:
            raise ValueError(f"Playlist {dst_playlist_id} is not a migration target")

        self.playlist = playlist
        self.playlist_id = int(playlist["id"])
        self.dst_service = playlist["service"]
        self.src_playlist_id = int(playlist["source_playlist_id"])

    def stats(self) -> dict:
        counts = db.match_counts(self.src_playlist_id, self.playlist_id)
        counts["playlist_id"] = self.playlist_id
        counts["pending"] = db.count_pending(self.src_playlist_id, self.playlist_id)
        return counts

    def apply(self, limit: int = BATCH_SIZE) -> dict:
        batch = db.pending_batch(self.src_playlist_id, self.playlist_id, limit)
        if not batch:
            return {"applied": 0, "remaining": 0, "done": True}

        token = db.get_setting(f"token-{self.dst_service}")
        client = choose_api(self.dst_service, token)

        ids = [row["dst_external_id"] for row in batch]
        sent = client.like_tracks(ids)
        logger.info("Liked %s tracks on %s", sent, self.dst_service)

        for row in batch:
            db.mark_applied(row["match_id"])

        remaining = db.count_pending(self.src_playlist_id, self.playlist_id)
        return {
            "applied": len(batch),
            "sent": sent,
            "remaining": remaining,
            "done": remaining == 0,
        }
