from app import db


def test_import_requires_token(client):
    # no client is constructed here: the guard fires first
    assert client.post("/api/import/yandex").status_code == 400
    assert client.post("/api/import/youtube").status_code == 400


def test_token_unlocks_import(client, fake):
    client.post("/api/token/yandex", json={"value": "y0-abc"})

    status = client.get("/api/status").json()
    assert status["statuses"]["yandex"]["has_token"] is True
    assert status["statuses"]["youtube"]["has_token"] is False

    assert client.post("/api/import/yandex").status_code == 200


def test_empty_token_rejected(client):
    assert client.post("/api/token/yandex", json={"value": "   "}).status_code == 400
    assert client.post("/api/import/yandex").status_code == 400


def test_import_creates_a_playlist(client, fake):
    client.post("/api/token/youtube", json={"value": "header-block"})
    response = client.post("/api/import/youtube")

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1

    playlist = db.get_playlist(body["playlist_id"])
    assert playlist.service == "youtube"
    assert playlist.source_playlist_id is None
    assert db.playlist_tracks(playlist.id)[0].track.title == "Blue Monday"


def test_each_import_is_a_separate_playlist(client, fake):
    client.post("/api/token/youtube", json={"value": "header-block"})

    first = client.post("/api/import/youtube").json()["playlist_id"]
    second = client.post("/api/import/youtube").json()["playlist_id"]

    assert first != second
    listed = client.get("/api/playlists").json()["playlists"]
    assert {playlist["id"] for playlist in listed} == {first, second}


def test_stale_youtube_token_gives_actionable_error(client, monkeypatch):
    def explode(*args, **kwargs):
        raise KeyError("Unable to find 'twoColumnBrowseResultsRenderer' using path [...]")

    monkeypatch.setattr("app.services.import_service.choose_api", explode)

    client.post("/api/token/youtube", json={"value": "stale-header-block"})
    response = client.post("/api/import/youtube")

    assert response.status_code == 401
    assert "paste a fresh one" in response.json()["detail"]


def test_network_failure_is_not_a_500(client, monkeypatch):
    def offline(*args, **kwargs):
        raise ConnectionError("Network is unreachable")

    monkeypatch.setattr("app.services.import_service.choose_api", offline)

    client.post("/api/token/yandex", json={"value": "y0-token"})
    response = client.post("/api/import/yandex")

    assert response.status_code == 502
    assert "cannot reach" in response.json()["detail"]
