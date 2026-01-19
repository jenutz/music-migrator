import logging

from app import crud
from app.integrations.factory import FULL_NAME, MusicService

logger = logging.getLogger(__name__)

EXPORTED_NAME = "Export"

DELIVERIES = ("likes", "playlist")


def create_target_playlist(
    src_playlist_id: int,
    dst_service: str,
    delivery: str = "likes",
    name: str | None = None,
) -> dict:
    source = crud.get_playlist(src_playlist_id)
    if not source:
        raise ValueError(f"Unknown playlist {src_playlist_id}")
    if source.source_playlist_id:
        raise ValueError("This playlist was already exported")

    service = MusicService(dst_service).value
    if delivery not in DELIVERIES:
        raise ValueError(f"Unknown delivery: {delivery}")

    if not crud.get_setting(f"token-{service}"):
        raise ValueError(f"Log in to {FULL_NAME[service]} first")

    playlist_id = crud.create_playlist(
        service=service,
        name=name or source.name,
        tracks=None,
        source_playlist_id=src_playlist_id,
        delivery=delivery,
    )
    logger.info(
        "Exporting playlist %s to %s as %s (%s)",
        src_playlist_id,
        service,
        playlist_id,
        delivery,
    )

    return {
        "playlist_id": playlist_id,
        "service": service,
        "delivery": delivery,
        "source_playlist_id": src_playlist_id,
    }
