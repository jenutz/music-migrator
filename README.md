# Music Migrator

Moves a liked-tracks library from one music service to another.

I had this sitting half-finished for about six months, so it got rebuilt on
SQLite with no user accounts — it is a one-person tool, so pretending it needed
a users table was just cost.

## How it works

1. Paste a token for a service (both optional, you only need the ones you use).
2. Import that service's liked tracks into the local database.
3. Open the workspace: it shows one source track at a time, searches the other
   service by `title + artist`, and ranks candidates by a fuzzy score
   (title, artist, duration, and a small penalty for music videos).
4. Pick the right one, or skip. Choices are saved immediately, so closing the
   tab costs nothing.
5. Hit the apply button. It likes the chosen tracks on the destination in
   source-playlist order, 50 at a time, and is safe to re-run — applied tracks
   are marked so they are not sent twice.

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

Data lives in `data/app.db` (or `$DATA_DIR/app.db`).

## Tokens

**Yandex Music** — https://yandex-music.readthedocs.io/en/main/token.html

**YouTube Music** — open https://music.youtube.com, F12 → Network, find a
`/browse` request, copy the whole request header block and paste it in.
Details: https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html

Neither token is written to the repo; `secrets/` and `data/` are gitignored.

## Tests

```sh
pytest tests -q
```

The HTTP tests stub out the service clients, so they run offline. They cover
the scoring rules, playlist ordering, the chosen → applied transition, and that
re-running apply does not double-like anything.

## Known rough edges

- YouTube's header token expires eventually; if import starts 401-ing, paste a
  fresh one.
- Search results are cached per track, so re-searching after editing the query
  is explicit (`Search` button / `refresh=true`) rather than automatic.
- Duration heuristics assume the two services agree on track length — live and
  extended versions need a manual pick.
