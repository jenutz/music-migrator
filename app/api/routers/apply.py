import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import load_playlist
from app.api.errors import explain
from app.services import ApplyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/apply", tags=["apply"])


@router.get("/stats")
def stats(playlist_id: int):
    try:
        return ApplyService(playlist_id).stats()
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("")
def apply(playlist_id: int, limit: int = 50):
    try:
        return ApplyService(playlist_id).apply(limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Apply failed")
        raise explain(exc, load_playlist(playlist_id).service)
