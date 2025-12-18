from fastapi import FastAPI, Request, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Annotated

import logging
logger = logging.getLogger("uvicorn")

from src.api.factory import choose_api, MusicService, FULL_NAME
from src.api.base_music_api import BaseMusicApi
import src.settings as settings
import src.track_store as track_store

app = FastAPI()
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")


def get_client(client: MusicService, token: str | None = None) ->BaseMusicApi:
    if not hasattr(app.state, "api_clients"):
        app.state.api_clients = dict()
    if client not in app.state.api_clients.keys():
        token = settings.get(f"token-{client.value}")
        app.state.api_clients[client] = choose_api(client, token)
    return app.state.api_clients[client]


def get_available_data():
    data_completed = []
    for s in MusicService:
        if settings.get(f"token-{s.value}"):
            data_completed.append(f"token-{s.value}")

        if track_store.is_stored(s):
            data_completed.append(f"store-{s.value}")
    
    return data_completed
    

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    data_completed = get_available_data()
    logger.critical(data_completed)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "services": [e.value for e in MusicService],
            "fullname": FULL_NAME,
            "data_completed":data_completed 
        }
    )

@app.get("/token-prompt/{service}")
def get_token_prompt(request:Request, service: MusicService):
    file_path = f"{service.value}-token-prompt.html"
    return templates.TemplateResponse(
        file_path,
        {"request": request})

@app.post("/enter-token/{service}")
async def enter_token(service: MusicService, value: Annotated[str, Body(embed=True)]):
    settings.set(f"token-{service.value}",value)


@app.post("/fetch-tracks/{service}")
async def fetch_tracks(service: MusicService):
    client = get_client(service)
    tracks = client.get_liked_tracks()
    track_store.save_tracks(tracks, service)




@app.get("/table/{service}", response_class=HTMLResponse)
def table(request: Request, service: MusicService):
    songs = track_store.load_tracks(service)
    return templates.TemplateResponse(
        "table.html",
        {
            "request": request,
            "songs": songs,
        "service": service.value
        }
    )



# @app.get("/compare", response_class=HTMLResponse)
# def compare(request: Request):
#     complement = db.get_complement()
#     return templates.TemplateResponse(
#         "table.html",
#         {
#             "request": request,
#             "songs": complement,
#     "service": "cmp" 
#         }
#     )


# @app.get("/search", response_class=HTMLResponse)
# def match(request: Request, track_id: str, src: str, dst: str):
#     src_client = choose_api(src)
#     dst_client = choose_api(dst)

#     target = src_client.get_track(track_id)
#     matches = dst_client.search(target['title'])

#     return templates.TemplateResponse(
#         "match.html",
#         {
#             "request": request,
#             "target": target,
#             "song_matches": matches
#         }
#     )

# @app.get("/test", response_class=HTMLResponse)
# def test(request: Request):
#     pass


# @app.post("/fetch-from")
# def fetch_music_service(data):
#     service_id = data.id