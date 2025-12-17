from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os

import db

### core functionality:
### 1. load from service into db = ugly but done
### 2. compare different dbs = ugly but done

### 3. search for song
### 4. upload


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    yt_exists = os.path.exists("tracks_yt.db")
    yd_exists = os.path.exists("tracks_yd.db")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "services": ["yt","yd"],
            "fullname": {"yt":"Youtube Music","yd":"Yandex Music"}
        }
    )

@app.get("/table", response_class=HTMLResponse)
def table(request: Request, service: str):
    allowed = {'yt', 'yd'}
    if service not in allowed:
        raise ValueError("Invalid service")

    songs = db.get_songs(service)
    return templates.TemplateResponse(
        "table.html",
        {
            "request": request,
            "songs": songs,
    "service": service 
        }
    )

@app.post("/load", response_class=HTMLResponse)
def load(request: Request, service: str):
    try:
        db.pull_songs(service)
    except KeyError as e:
        print(e)
        return f"Authentication is stale or playlist unavailable."
    except Exception as e:
        print(e)
        return f"An unexpected error occurred: {type(e).__name__} {e}"
    return f"<p>Файл tracks.db создан ✅</p>"

@app.get("/compare", response_class=HTMLResponse)
def compare(request: Request):
    complement = db.get_complement()
    return templates.TemplateResponse(
        "table.html",
        {
            "request": request,
            "songs": complement,
    "service": "cmp" 
        }
    )



@app.get("/search", response_class=HTMLResponse)
def search(request: Request):
    from ytmusicapi import YTMusic
    title="smoke on the water"
    ytmusic = YTMusic('browser.json')
    matches = ytmusic.search(title)

    res = []
    for m in (m for m in matches if m['resultType']=='song'):
        m['artists']= ','.join(e['name'] for e in m['artists'])
        m['thumbnails']=m['thumbnails'][0]['url']
        res.append(m)


    
    print('\n'.join(str(e) for e in res))
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "songs": res,
            "title": title
        }
    )


@app.get("/test", response_class=HTMLResponse)
def test(request: Request):
    from yandex_music import Client
    with open("yandex.key", "r") as file:
        API_KEY = file.read().rstrip()
    client = Client(API_KEY).init()
    songs = client.tracks()


def normid_yt_track(track):
    all_thumbnails = track['videoDetails']['thumbnail']['thumbnails']
    defalt_thumbnail = all_thumbnails[-1] if all_thumbnails else None
    thumbnail = next((e for e in all_thumbnails if e['width'] >= 200), defalt_thumbnail)['url']
    return {
        'title': track['videoDetails']['title'],
        'artists': track['videoDetails']['author'],
        'album': track.get('album', None),
        'thumbnail' : thumbnail,
        'length_s' :track['videoDetails']['lengthSeconds']
    }

def norm_search_yt_track(track):
    all_thumbnails = track['thumbnails']
    defalt_thumbnail = all_thumbnails[-1] if all_thumbnails else None
    thumbnail = next((e for e in all_thumbnails if e['width'] >= 200), defalt_thumbnail)['url']
    return {
        'title': track['title'],
        'artists': ', '.join(str(e['name']) for e in track['artists']),
        'album': track.get('album', None),
        'thumbnail' : thumbnail,
        'duration_s' :track.get('duration_seconds')
    }

def norm_yd_track(track):
    return {
        'title': track.title,
        'artists': ', '.join(e.name for e in track.artists),
        'album': track.albums[0].title,
        'thumbnail' : track.albums[0].get_cover_url('200x200'),
        'duration_s' :track.duration_ms//1000
    }




from yandex_music import Client
with open("yandex.key", "r") as file:
    API_KEY = file.read().rstrip()
ydmusic = Client(API_KEY).init()

from ytmusicapi import YTMusic
ytmusic = YTMusic('browser.json')

@app.get("/match", response_class=HTMLResponse)
def match(request: Request, song_id: str):
# def add(request: Request, song: str, src: str, dst: str):
    target = norm_yd_track(ydmusic.tracks(song_id)[0])

    matches = ytmusic.search(target['title'])
    matches = [norm_search_yt_track(m) for m in matches if m['resultType']=='song']

    return templates.TemplateResponse(
        "match.html",
        {
            "request": request,
            "target": target,
            "song_matches": matches
        }
    )

@app.get("/match2", response_class=HTMLResponse)
def match2(request: Request, song_id: str):
    target = normid_yt_track(ytmusic.get_song(videoId=song_id))
    matches = ydmusic.search(target['title'], type_='track').tracks.results
    matches = [norm_yd_track(m) for m in matches]
    return templates.TemplateResponse(
        "match.html",
        {
            "request": request,
            "target": target,
            "song_matches": matches
        }
    )


