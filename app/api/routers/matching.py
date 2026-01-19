import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import load_playlist
from app.api.errors import explain
from app.schemas import ChoosePayload
from app.services import MatchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["matching"])


@router.get("/candidates/{src_track_id}")
def candidates(
    src_track_id: int,
    playlist_id: int,
    refresh: bool = False,
    query: str | None = None,
):
    try:
        service = MatchService(playlist_id)
        return {"candidates": service.candidates(src_track_id, refresh=refresh, query=query)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Search failed")
        raise explain(exc, load_playlist(playlist_id).service)


@router.post("/choose/{src_track_id}")
def choose(src_track_id: int, playlist_id: int, payload: ChoosePayload):
    try:
        return MatchService(playlist_id).choose_by_id(src_track_id, payload.external_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/skip/{src_track_id}")
def skip(src_track_id: int, playlist_id: int):
    try:
        return MatchService(playlist_id).skip(src_track_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
