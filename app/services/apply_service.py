"""Push the chosen matches to the destination service's liked library."""

import logging

from app import db
from app.integrations.factory import choose_api

logger = logging.getLogger(__name__)

# Services rate-limit aggressively; keep batches small and resumable.
BATCH_SIZE = 50


class ApplyService:
    """Likes every chosen track on the destination, in source playlist order."""

    def __init__(self, dst_service: str, src_service: str):
        self.dst_service = dst_service
        self.src_service = src_service

    def _playlist(self) -> dict:
        playlist = db.get_liked_playlist(self.src_service)
        if not playlist:
            raise ValueError(f"No imported library for {self.src_service}")
        return dict(playlist)

    def stats(self) -> dict:
        playlist = self._playlist()
        counts = db.match_counts(playlist["id"], self.dst_service)
        counts["playlist_id"] = playlist["id"]
        counts["pending"] = db.count_pending(playlist["id"], self.dst_service)
        return counts

    def apply(self, limit: int = BATCH_SIZE) -> dict:
        playlist = self._playlist()
        batch = db.pending_batch(playlist["id"], self.dst_service, limit)
        if not batch:
            return {"applied": 0, "remaining": 0, "done": True}

        token = db.get_setting(f"token-{self.dst_service}")
        client = choose_api(self.dst_service, token)

        ids = [row["dst_external_id"] for row in batch]
        sent = client.like_tracks(ids)
        logger.info("Liked %s tracks on %s", sent, self.dst_service)

        for row in batch:
            db.mark_applied(row["match_id"])

        remaining = db.count_pending(playlist["id"], self.dst_service)
        return {
            "applied": len(batch),
            "sent": sent,
            "remaining": remaining,
            "done": remaining == 0,
        }
