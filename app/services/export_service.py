"""Turn an imported playlist into a target playlist on another service."""

import logging

from app import db
from app.integrations.factory import FULL_NAME, MusicService

logger = logging.getLogger(__name__)

EXPORTED_NAME = "Экспорт"


def create_target_playlist(src_playlist_id: int, dst_service: str) -> dict:
    """Create a playlist on `dst_service` that will be filled from the source."""
    source = db.get_playlist(src_playlist_id)
    if not source:
        raise ValueError(f"Unknown playlist {src_playlist_id}")
    if source["source_playlist_id"]:
        raise ValueError("Нельзя экспортировать уже экспортированный плейлист")

    service = MusicService(dst_service).value
    if service == source["service"]:
        raise ValueError("Плейлист уже принадлежит этому сервису")

    if not db.get_setting(f"token-{service}"):
        raise ValueError(f"Сначала войдите в {FULL_NAME[service]}")

    playlist_id = db.create_playlist(
        service=service,
        name=EXPORTED_NAME,
        tracks=None,
        source_playlist_id=src_playlist_id,
    )
    logger.info("Exporting playlist %s to %s as %s", src_playlist_id, service, playlist_id)

    return {"playlist_id": playlist_id, "service": service, "source_playlist_id": src_playlist_id}
