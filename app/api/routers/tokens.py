import logging

from fastapi import APIRouter, Depends, HTTPException

from app import crud
from app.api.deps import get_service
from app.integrations import MusicService, reset_cache
from app.schemas import TokenPayload
from app.services import yandex_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tokens"])


@router.post("/token/{service}")
def set_token(payload: TokenPayload, svc: MusicService = Depends(get_service)):
    value = payload.value.strip()
    if not value:
        raise HTTPException(400, "Empty token")

    crud.set_setting(f"token-{svc.value}", value)
    reset_cache()
    logger.info("Stored token for %s", svc.value)
    return {"service": svc.value, "saved": True}


@router.delete("/token/{service}")
def clear_token(svc: MusicService = Depends(get_service)):
    crud.set_setting(f"token-{svc.value}", "")
    reset_cache()
    if svc is MusicService.yandex:
        yandex_auth.reset()
    return {"service": svc.value, "cleared": True}
