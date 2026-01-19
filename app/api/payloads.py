from app import crud
from app.integrations import FULL_NAME
from app.models import Playlist


def playlist_payload(playlist: Playlist) -> dict:
    counts = crud.playlist_counts(playlist)
    source = crud.get_playlist(playlist.source_playlist_id) if playlist.source_playlist_id else None
    return {
        "id": playlist.id,
        "service": playlist.service,
        "service_name": FULL_NAME.get(playlist.service, playlist.service),
        "name": playlist.name,
        "created_at": playlist.created_at,
        "kind": playlist.kind,
        "delivery": playlist.delivery,
        "remote_playlist_id": playlist.remote_playlist_id,
        "source_playlist_id": playlist.source_playlist_id,
        "source_name": source.name if source else None,
        "source_service": source.service if source else None,
        "source_service_name": FULL_NAME.get(source.service, source.service) if source else None,
        "source_created_at": source.created_at if source else None,
        **counts,
    }
