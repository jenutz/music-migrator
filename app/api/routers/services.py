import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_service
from app.api.errors import explain
from app.integrations import MusicService
from app.services import clear_likes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/service", tags=["services"])


@router.post("/{service}/clear-likes")
def clear_service_likes(svc: MusicService = Depends(get_service)):
    try:
        return clear_likes(svc.value)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Clearing likes failed for %s", svc.value)
        raise explain(exc, svc.value)
