import logging

from app import db
from app.integrations.factory import FULL_NAME, MusicService

logger = logging.getLogger(__name__)

EXPORTED_NAME = "Экспорт"

DELIVERIES = ("likes", "playlist")


def create_target_playlist(
    src_playlist_id: int,
    dst_service: str,
    delivery: str = "likes",
    name: str | None = None,
) -> dict:
    """`dst_service` may be the source's own service: that is how a liked
    library becomes a real playlist without leaving the app."""
    source = db.get_playlist(src_playlist_id)
    if not source:
        raise ValueError(f"Unknown playlist {src_playlist_id}")
    if source.source_playlist_id:
        raise ValueError("Нельзя экспортировать уже экспортированный плейлист")

    service = MusicService(dst_service).value
    if delivery not in DELIVERIES:
        raise ValueError(f"Unknown delivery: {delivery}")

    if not db.get_setting(f"token-{service}"):
        raise ValueError(f"Сначала войдите в {FULL_NAME[service]}")

    # `name` is what the destination playlist gets called; the sidebar labels
    # targets by date, so it does not need to be the local row label.
    playlist_id = db.create_playlist(
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
