# Music Migrator

Moves a liked-tracks library from one music service to another.

I had this sitting half-finished for about six months, so it got rebuilt on
SQLite with no user accounts — it is a one-person tool, so pretending it needed
a users table was just cost.

## How it works

Playlists are the unit of work, not services. A service row only logs in and
imports; everything you review and apply happens inside a playlist.

1. Connect a service — for Yandex press **Войти через Яндекс** and confirm the
   code on the Yandex page; YouTube still takes a pasted header block.
2. **Загрузить** snapshots that service's liked tracks into a new playlist,
   listed in the sidebar under the service with the date it was imported.
   Importing again creates another playlist instead of overwriting the old one.
3. **Экспорт** on a playlist creates a *target* playlist on the other service.
   Several targets can exist for the same source, each with its own choices.
4. In the target playlist: one source track at a time, searched on the other
   service by `title + artist` and ranked by a fuzzy score (title, artist,
   duration, and a small penalty for music videos). Pick one or skip; choices
   are saved immediately.
5. Hit the apply button. It likes the chosen tracks on the destination in
   source-playlist order, 50 at a time, and is safe to re-run — applied tracks
   are marked so they are not sent twice. The sidebar row shows the progress.

Deleting a playlist cascades: dropping an import also drops the targets made
from it, while deleting a target leaves the source alone.

## Running it

```sh
docker compose up --build
# http://localhost:8000
```

Locally without Docker:

```sh
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Data lives in `data/app.db` (or `$DATA_DIR/app.db`). Compose bind-mounts
`./data`, so the database is a normal file you own - open it with any sqlite
client, copy it, and it survives `docker compose down -v`.

## Tokens

**Yandex Music** — press **Войти через Яндекс** in the sidebar: the app asks
Yandex for a device code, shows it, and waits for you to confirm it on
https://ya.ru/device. The token is saved to the local database. A manually
pasted token still works as a fallback
(https://yandex-music.readthedocs.io/en/main/token.html).

**YouTube Music** — open https://music.youtube.com, F12 → Network, find a
`/browse` request, copy the whole request header block and paste it in.
Details: https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html

Neither token is written to the repo; `secrets/` and `data/` are gitignored.
The device flow also stores `refresh_token` and the expiry timestamp, but the
`yandex-music` library does not refresh tokens on its own — when the token
expires, run the login again.

## Tests

```sh
pytest tests -q
```

The HTTP tests stub out the service clients, so they run offline. They cover
the scoring rules, playlist ordering, per-playlist scoping of choices, the
chosen → applied transition, and that re-running apply does not double-like
anything.

## Known rough edges

- YouTube's header token expires eventually; if import starts 401-ing, paste a
  fresh one.
- There is no rename: playlists are identified by their import/export time.
- A target playlist holds matches, not copies, so it only lists tracks that
  were chosen in it.
- Search results are cached per track, so re-searching after editing the query
  is explicit (`Search` button / `refresh=true`) rather than automatic.
- Duration heuristics assume the two services agree on track length — live and
  extended versions need a manual pick.
