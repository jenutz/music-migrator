import logging

from fastapi import APIRouter, Depends, HTTPException

from app import crud
from app.api.deps import get_service
from app.api.errors import explain
from app.api.payloads import playlist_payload
from app.integrations import MusicService
from app.services import ImportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import", tags=["imports"])


@router.post("/{service}")
def import_library(svc: MusicService = Depends(get_service)):
    try:
        result = ImportService(svc.value).run()
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Import failed for %s", svc.value)
        raise explain(exc, svc.value)

    result["playlist"] = playlist_payload(crud.get_playlist(result["playlist_id"]))
    return result
