"""Operations on a service's own liked library, not on our copies of it."""

import logging

from app import db
from app.integrations.factory import FULL_NAME, MusicService, choose_api

logger = logging.getLogger(__name__)

CLEAR_BATCH = 100


def _client(service: MusicService):
    token = db.get_setting(f"token-{service.value}")
    if not token:
        raise ValueError(f"Сначала войдите в {FULL_NAME[service.value]}")
    return choose_api(service.value, token)


def liked_count(service: MusicService) -> int:
    return len(_client(service).get_liked_tracks())


def clear_likes(service: str) -> dict:
    """Remove every track from the liked library of `service`.

    Only the service is touched: imported snapshots and match tables stay as
    they are, so a cleared library can still be compared against.
    """
    svc = MusicService(service)
    client = _client(svc)

    track_ids = [t["external_id"] for t in client.get_liked_tracks() if t.get("external_id")]
    logger.warning("Clearing %s liked tracks from %s", len(track_ids), svc.value)

    removed = 0
    for start in range(0, len(track_ids), CLEAR_BATCH):
        removed += client.unlike_tracks(track_ids[start : start + CLEAR_BATCH])

    return {"service": svc.value, "removed": removed}
