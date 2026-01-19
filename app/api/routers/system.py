from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.context import dashboard_context
from app.integrations import MusicService

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return JSONResponse({"status": "ok", "services": [s.value for s in MusicService]})


@router.get("/api/status")
def status():
    return dashboard_context()
