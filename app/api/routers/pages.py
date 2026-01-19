import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app import crud
from app.api.context import dashboard_context
from app.api.deps import get_target_playlist
from app.core.templating import templates
from app.integrations import FULL_NAME
from app.models import Playlist

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    context = dashboard_context()
    context["time"] = int(time.time())
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/migrate/{playlist_id}", response_class=HTMLResponse)
def migrate_page(request: Request, playlist: Playlist = Depends(get_target_playlist)):
    source = crud.get_playlist(playlist.source_playlist_id)

    context = dashboard_context()
    context.update(
        {
            "time": int(time.time()),
            "playlist": playlist,
            "playlist_id": playlist.id,
            "src_service": source.service,
            "src_created_at": source.created_at,
            "dst_service": playlist.service,
            "delivery": playlist.delivery or "likes",
            "src_name": FULL_NAME[source.service],
            "dst_name": FULL_NAME[playlist.service],
        }
    )
    return templates.TemplateResponse(request, "migrate.html", context)
