import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import db
from app.integrations import FULL_NAME, MusicService, reset_cache
from app.services import (
    ApplyService,
    ImportService,
    MatchService,
    clear_likes,
    create_target_playlist,
    yandex_auth,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    logger.info("Database ready at %s", db.DB_PATH)
    yield


app = FastAPI(title="Music Migrator", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _service(value: str) -> MusicService:
    try:
        return MusicService(value)
    except ValueError:
        raise HTTPException(404, f"Unknown service: {value}")


def _playlist(playlist_id: int) -> db.Playlist:
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(404, f"Unknown playlist {playlist_id}")
    return playlist


def _target_playlist(playlist_id: int) -> db.Playlist:
    playlist = _playlist(playlist_id)
    if not playlist.source_playlist_id:
        raise HTTPException(400, "Этот плейлист не является целью переноса")
    return playlist


def _playlist_payload(playlist: db.Playlist) -> dict:
    counts = db.playlist_counts(playlist)
    source = db.get_playlist(playlist.source_playlist_id) if playlist.source_playlist_id else None
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


TOKEN_HELP = {
    "yandex": 'Токен: <a href="https://yandex-music.readthedocs.io/en/main/token.html" '
              'target="_blank" rel="noopener">инструкция</a>',
    "youtube": 'Откройте <a href="https://music.youtube.com" target="_blank" rel="noopener">music.youtube.com</a>, '
               'F12 → Network, найдите запрос с "/browse" и скопируйте заголовки целиком.',
}


def dashboard_context() -> dict:
    statuses = {s.value: ImportService.status(s.value) for s in MusicService}
    return {
        "statuses": statuses,
        "fullname": FULL_NAME,
        "services": [s.value for s in MusicService],
        "token_help": TOKEN_HELP,
    }


# Client libraries raise huge, opaque errors; translate the common ones.
_AUTH_HINTS = (
    "twoColumnBrowseResultsRenderer",
    "signInEndpoint",
    "Sign in to listen",
)


def _explain(exc: Exception, service: str) -> HTTPException:
    text = str(exc)

    if any(hint in text for hint in _AUTH_HINTS):
        return HTTPException(401, f"{service}: token expired or invalid, paste a fresh one")

    if "Unauthorized" in text or "unauthorized" in text or "401" in text[:200]:
        return HTTPException(401, f"{service}: token rejected by the service")

    if "Network" in text or "ConnectionError" in type(exc).__name__:
        return HTTPException(502, f"{service}: cannot reach the service ({type(exc).__name__})")

    return HTTPException(502, f"{service}: {type(exc).__name__}: {text[:300]}")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    context = dashboard_context()
    context["time"] = int(time.time())
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/migrate/{playlist_id}", response_class=HTMLResponse)
def migrate_page(request: Request, playlist_id: int):
    playlist = _target_playlist(playlist_id)
    source = _playlist(playlist.source_playlist_id)

    context = dashboard_context()
    context.update(
        {
            "time": int(time.time()),
            "playlist": playlist,
            "playlist_id": playlist_id,
            "src_service": source.service,
            "src_created_at": source.created_at,
            "dst_service": playlist.service,
            "delivery": playlist.delivery or "likes",
            "src_name": FULL_NAME[source.service],
            "dst_name": FULL_NAME[playlist.service],
        }
    )
    return templates.TemplateResponse(request, "migrate.html", context)


class TokenPayload(BaseModel):
    value: str


@app.post("/api/token/{service}")
def set_token(service: str, payload: TokenPayload):
    svc = _service(service)
    value = payload.value.strip()
    if not value:
        raise HTTPException(400, "Empty token")

    db.set_setting(f"token-{svc.value}", value)
    reset_cache()  # force clients to rebuild with the new credentials
    logger.info("Stored token for %s", svc.value)
    return {"service": svc.value, "saved": True}


@app.delete("/api/token/{service}")
def clear_token(service: str):
    svc = _service(service)
    db.set_setting(f"token-{svc.value}", "")
    reset_cache()
    if svc is MusicService.yandex:
        yandex_auth.reset()
    return {"service": svc.value, "cleared": True}


@app.post("/api/auth/yandex/start")
def yandex_auth_start():
    """Begin the device flow. Returns at once; the page polls for the result."""
    return yandex_auth.start()


@app.get("/api/auth/yandex/status")
def yandex_auth_status():
    return yandex_auth.status()


@app.post("/api/auth/yandex/cancel")
def yandex_auth_cancel():
    return yandex_auth.cancel()


@app.get("/api/status")
def status():
    return dashboard_context()


@app.post("/api/import/{service}")
def import_library(service: str):
    svc = _service(service)
    try:
        result = ImportService(svc.value).run()
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # network / auth errors from the service
        logger.exception("Import failed for %s", svc.value)
        raise _explain(exc, svc.value)

    playlist = db.get_playlist(result["playlist_id"])
    result["playlist"] = _playlist_payload(playlist)
    return result


@app.get("/api/playlists")
def playlists():
    return {"playlists": [_playlist_payload(p) for p in db.list_playlists()]}


@app.get("/api/playlist/{playlist_id}")
def playlist_detail(playlist_id: int):
    """Everything a playlist view needs: its tracks, or its match table."""
    playlist = _playlist(playlist_id)
    payload = _playlist_payload(playlist)

    if payload["kind"] == "imported":
        tracks = [entry.as_dict() for entry in db.playlist_tracks(playlist_id)]
    else:
        tracks = db.ordered_matches(playlist.source_playlist_id, playlist_id)

    return {"playlist": payload, "tracks": tracks}


@app.delete("/api/playlist/{playlist_id}")
def delete_playlist(playlist_id: int):
    _playlist(playlist_id)
    db.delete_playlist(playlist_id)
    return {"deleted": playlist_id}


class ExportPayload(BaseModel):
    dst_service: str
    delivery: str = "playlist"
    name: str | None = None


@app.post("/api/export/{playlist_id}")
def export_playlist(playlist_id: int, payload: ExportPayload):
    try:
        result = create_target_playlist(
            playlist_id,
            payload.dst_service,
            delivery=payload.delivery,
            name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    playlist = db.get_playlist(result["playlist_id"])
    result["playlist"] = _playlist_payload(playlist)
    return result


@app.get("/api/tracks")
def tracks(playlist_id: int):
    playlist = _target_playlist(playlist_id)
    return {
        "playlist": _playlist_payload(playlist),
        "counts": db.match_counts(playlist.source_playlist_id, playlist_id),
        "tracks": db.ordered_matches(playlist.source_playlist_id, playlist_id),
    }


@app.get("/api/candidates/{src_track_id}")
def candidates(src_track_id: int, playlist_id: int, refresh: bool = False, query: str | None = None):
    try:
        service = MatchService(playlist_id)
        return {"candidates": service.candidates(src_track_id, refresh=refresh, query=query)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Search failed")
        raise _explain(exc, _playlist(playlist_id).service)


class ChoosePayload(BaseModel):
    external_id: str


@app.post("/api/choose/{src_track_id}")
def choose(src_track_id: int, playlist_id: int, payload: ChoosePayload):
    try:
        return MatchService(playlist_id).choose_by_id(src_track_id, payload.external_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/skip/{src_track_id}")
def skip(src_track_id: int, playlist_id: int):
    try:
        return MatchService(playlist_id).skip(src_track_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/service/{service}/clear-likes")
def clear_service_likes(service: str):
    """Empty the liked library on the service itself. Irreversible."""
    svc = _service(service)
    try:
        return clear_likes(svc.value)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Clearing likes failed for %s", svc.value)
        raise _explain(exc, svc.value)


@app.get("/api/apply/stats")
def apply_stats(playlist_id: int):
    try:
        return ApplyService(playlist_id).stats()
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/apply")
def apply(playlist_id: int, limit: int = 50):
    try:
        return ApplyService(playlist_id).apply(limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Apply failed")
        raise _explain(exc, _playlist(playlist_id).service)


@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "services": [s.value for s in MusicService]})
