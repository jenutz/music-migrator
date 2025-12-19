"""Music library migrator.

Single-user app: import the liked library from one service, review each track
against search results on the other service, then like the chosen tracks.
"""

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
from app.services import ApplyService, ImportService, MatchService

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


# --- helpers --------------------------------------------------------------


def _service(value: str) -> MusicService:
    try:
        return MusicService(value)
    except ValueError:
        raise HTTPException(404, f"Unknown service: {value}")


def _pair(src: str, dst: str) -> tuple[MusicService, MusicService]:
    source, dest = _service(src), _service(dst)
    if source is dest:
        raise HTTPException(400, "Source and destination must differ")
    return source, dest


def dashboard_context() -> dict:
    statuses = {s.value: ImportService.status(s.value) for s in MusicService}
    return {
        "statuses": statuses,
        "fullname": FULL_NAME,
        "services": [s.value for s in MusicService],
    }


# Client libraries raise huge, opaque errors. Translate the common ones so the
# UI can show a sentence instead of a wall of JSON.
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


# --- pages ----------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    context = dashboard_context()
    context["time"] = int(time.time())
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/migrate/{src}/{dst}", response_class=HTMLResponse)
def migrate_page(request: Request, src: str, dst: str):
    source, dest = _pair(src, dst)
    context = dashboard_context()
    context.update(
        {
            "time": int(time.time()),
            "src": source.value,
            "dst": dest.value,
            "src_name": FULL_NAME[source.value],
            "dst_name": FULL_NAME[dest.value],
        }
    )
    return templates.TemplateResponse(request, "migrate.html", context)


# --- tokens ---------------------------------------------------------------


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
    return {"service": svc.value, "cleared": True}


# --- import ---------------------------------------------------------------


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

    result.update(ImportService.status(svc.value))
    return result


# --- matching -------------------------------------------------------------


@app.get("/api/tracks")
def tracks(src: str, dst: str):
    source, dest = _pair(src, dst)
    playlist = db.get_liked_playlist(source.value)
    if not playlist:
        return {"tracks": [], "counts": db.match_counts(0, dest.value), "playlist_id": None}

    rows = db.ordered_matches(playlist["id"], dest.value)
    counts = db.match_counts(playlist["id"], dest.value)
    return {
        "playlist_id": playlist["id"],
        "counts": counts,
        "tracks": [dict(row) for row in rows],
    }


@app.get("/api/candidates/{src_track_id}")
def candidates(src_track_id: int, dst: str, refresh: bool = False, query: str | None = None):
    _service(dst)
    try:
        return {"candidates": MatchService(dst).candidates(src_track_id, refresh=refresh, query=query)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Search failed")
        raise _explain(exc, dst)


class ChoosePayload(BaseModel):
    external_id: str


@app.post("/api/choose/{src_track_id}")
def choose(src_track_id: int, dst: str, payload: ChoosePayload):
    _service(dst)
    try:
        return MatchService(dst).choose_by_id(src_track_id, payload.external_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/skip/{src_track_id}")
def skip(src_track_id: int, dst: str):
    _service(dst)
    return MatchService(dst).skip(src_track_id)


# --- apply ----------------------------------------------------------------


@app.get("/api/apply/stats")
def apply_stats(src: str, dst: str):
    source, dest = _pair(src, dst)
    return ApplyService(dest.value, source.value).stats()


@app.post("/api/apply")
def apply(src: str, dst: str, limit: int = 50):
    source, dest = _pair(src, dst)
    try:
        return ApplyService(dest.value, source.value).apply(limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Apply failed")
        raise _explain(exc, dest.value)


@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "services": [s.value for s in MusicService]})
