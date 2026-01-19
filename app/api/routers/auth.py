from fastapi import APIRouter

from app.services import yandex_auth

router = APIRouter(prefix="/api/auth/yandex", tags=["yandex auth"])


@router.post("/start")
def start():
    return yandex_auth.start()


@router.get("/status")
def status():
    return yandex_auth.status()


@router.post("/cancel")
def cancel():
    return yandex_auth.cancel()
