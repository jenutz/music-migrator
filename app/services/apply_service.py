"""Push the chosen matches of one target playlist to the destination service."""

import logging

from app import db
from app.integrations.factory import choose_api

logger = logging.getLogger(__name__)

# Services rate-limit aggressively; keep batches small and resumable.
BATCH_SIZE = 50


class ApplyService:
    """Delivers every chosen track of a target playlist, in source playlist order.

    Two ways to deliver: like them (``likes``) or build a playlist on the
    destination service (``playlist``). The latter creates the remote playlist
    on the first batch and appends to it afterwards, so an interrupted run
    resumes into the same playlist instead of making a second one.
    """

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
        self.delivery = playlist["delivery"] or "likes"

    def stats(self) -> dict:
        counts = db.match_counts(self.src_playlist_id, self.playlist_id)
        counts["playlist_id"] = self.playlist_id
        counts["pending"] = db.count_pending(self.src_playlist_id, self.playlist_id)
        counts["delivery"] = self.delivery
        counts["remote_playlist_id"] = self.playlist["remote_playlist_id"]
        return counts

    def _deliver_to_playlist(self, client, ids: list[str]) -> int:
        # Re-read: an earlier batch may have created the remote playlist.
        remote_id = db.get_playlist(self.playlist_id)["remote_playlist_id"]

        if remote_id:
            return client.add_playlist_tracks(remote_id, ids)

        remote_id = client.create_playlist(self.playlist["name"], ids)
        db.set_remote_playlist(self.playlist_id, remote_id)
        logger.info("Created playlist %s on %s", remote_id, self.dst_service)
        return len(ids)

    def apply(self, limit: int = BATCH_SIZE) -> dict:
        batch = db.pending_batch(self.src_playlist_id, self.playlist_id, limit)
        if not batch:
            return {"applied": 0, "sent": 0, "remaining": 0, "done": True}

        token = db.get_setting(f"token-{self.dst_service}")
        client = choose_api(self.dst_service, token)

        ids = [row["dst_external_id"] for row in batch]
        if self.delivery == "playlist":
            sent = self._deliver_to_playlist(client, ids)
            logger.info("Added %s tracks to a playlist on %s", sent, self.dst_service)
        else:
            sent = client.like_tracks(ids)
            logger.info("Liked %s tracks on %s", sent, self.dst_service)

        if sent != len(ids):
            logger.warning(
                "%s accepted %s of %s tracks; marking the batch anyway", self.dst_service, sent, len(ids)
            )

        for row in batch:
            db.mark_applied(row["match_id"])

        remaining = db.count_pending(self.src_playlist_id, self.playlist_id)
        return {
            "applied": len(batch),
            "sent": sent,
            "delivery": self.delivery,
            "remaining": remaining,
            "done": remaining == 0,
        }
