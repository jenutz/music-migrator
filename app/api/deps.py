from fastapi import Depends, HTTPException, Path

from app import crud
from app.integrations import MusicService
from app.models import Playlist


def get_service(service: str = Path(...)) -> MusicService:
    try:
        return MusicService(service)
    except ValueError:
        raise HTTPException(404, f"Unknown service: {service}")


def load_playlist(playlist_id: int) -> Playlist:
    playlist = crud.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(404, f"Unknown playlist {playlist_id}")
    return playlist


def load_target_playlist(playlist_id: int) -> Playlist:
    playlist = load_playlist(playlist_id)
    if not playlist.source_playlist_id:
        raise HTTPException(400, "This playlist is not a migration target")
    return playlist


def get_playlist(playlist_id: int = Path(...)) -> Playlist:
    return load_playlist(playlist_id)


def get_target_playlist(playlist: Playlist = Depends(get_playlist)) -> Playlist:
    if not playlist.source_playlist_id:
        raise HTTPException(400, "This playlist is not a migration target")
    return playlist
