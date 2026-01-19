from fastapi import APIRouter, Depends, HTTPException

from app import crud
from app.api.deps import get_playlist, load_target_playlist
from app.api.payloads import playlist_payload
from app.models import Playlist
from app.schemas import ExportPayload
from app.services import create_target_playlist

router = APIRouter(prefix="/api", tags=["playlists"])


@router.get("/playlists")
def playlists():
    return {"playlists": [playlist_payload(p) for p in crud.list_playlists()]}


@router.get("/playlist/{playlist_id}")
def playlist_detail(playlist: Playlist = Depends(get_playlist)):
    payload = playlist_payload(playlist)

    if payload["kind"] == "imported":
        tracks = [entry.as_dict() for entry in crud.playlist_tracks(playlist.id)]
    else:
        tracks = crud.ordered_matches(playlist.source_playlist_id, playlist.id)

    return {"playlist": payload, "tracks": tracks}


@router.delete("/playlist/{playlist_id}")
def delete_playlist(playlist: Playlist = Depends(get_playlist)):
    crud.delete_playlist(playlist.id)
    return {"deleted": playlist.id}


@router.post("/export/{playlist_id}")
def export_playlist(payload: ExportPayload, playlist: Playlist = Depends(get_playlist)):
    try:
        result = create_target_playlist(
            playlist.id,
            payload.dst_service,
            delivery=payload.delivery,
            name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    result["playlist"] = playlist_payload(crud.get_playlist(result["playlist_id"]))
    return result


@router.get("/tracks")
def tracks(playlist_id: int):
    playlist = load_target_playlist(playlist_id)
    return {
        "playlist": playlist_payload(playlist),
        "counts": crud.match_counts(playlist.source_playlist_id, playlist.id),
        "tracks": crud.ordered_matches(playlist.source_playlist_id, playlist.id),
    }
