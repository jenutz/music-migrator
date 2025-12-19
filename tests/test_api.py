"""HTTP API tests using the FastAPI test client and a stubbed music client."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.integrations.factory import reset_cache
from app.main import app


class FakeClient:
    """Stands in for a real service so tests stay offline and deterministic."""

    def __init__(self, results=None):
        self.results = results or []
        self.liked = []

    def get_liked_tracks(self):
        return [
            {
                "service": "youtube",
                "external_id": "yt-blue-monday",
                "title": "Blue Monday",
                "artists": "New Order",
                "album": "Power, Corruption & Lies",
                "thumbnail": None,
                "duration_s": 450,
            }
        ]

    def search(self, query, limit=10):
        return self.results

    def like_tracks(self, ids):
        self.liked.extend(ids)
        return len(ids)

    def unlike_tracks(self, ids):
        return 0


@pytest.fixture
def client():
    reset_cache()
    with TestClient(app) as test_client:
        yield test_client
    reset_cache()


@pytest.fixture
def fake(monkeypatch):
    fake_client = FakeClient(
        results=[
            {"service": "youtube", "external_id": "yt-1", "title": "Blue Monday",
             "artists": "New Order", "album": "Power, Corruption & Lies",
             "thumbnail": None, "duration_s": 450, "result_type": "song"},
            {"service": "youtube", "external_id": "yt-2", "title": "Blue Monday (Live)",
             "artists": "New Order", "album": None,
             "thumbnail": None, "duration_s": 800, "result_type": "video"},
        ]
    )
    monkeypatch.setattr("app.services.import_service.choose_api", lambda *a, **k: fake_client)
    monkeypatch.setattr("app.services.match_service.choose_api", lambda *a, **k: fake_client)
    monkeypatch.setattr("app.services.apply_service.choose_api", lambda *a, **k: fake_client)
    return fake_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Music Migrator" in response.text


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


def test_import_stores_library(client, fake):
    client.post("/api/token/youtube", json={"value": "header-block"})
    response = client.post("/api/import/youtube")

    assert response.status_code == 200
    assert response.json()["imported"] == 1

    rows = db.get_playlist_tracks(db.get_liked_playlist("youtube")["id"])
    assert rows[0]["title"] == "Blue Monday"


def test_full_flow(client, fake):
    client.post("/api/token/youtube", json={"value": "header-block"})
    client.post("/api/token/yandex", json={"value": "y0-token"})
    client.post("/api/import/youtube")

    playlist_id = db.get_liked_playlist("youtube")["id"]
    src_track_id = db.get_playlist_tracks(playlist_id)[0]["id"]

    # candidates are ranked, best first -- the live-only video must lose
    candidates = client.get(f"/api/candidates/{src_track_id}?dst=yandex").json()["candidates"]
    assert [c["external_id"] for c in candidates] == ["yt-1", "yt-2"]
    assert candidates[0]["score"] > candidates[1]["score"]

    # pick the best one
    chosen = client.post(f"/api/choose/{src_track_id}?dst=yandex", json={"external_id": "yt-1"})
    assert chosen.status_code == 200

    stats = client.get("/api/apply/stats?src=youtube&dst=yandex").json()
    assert (stats["chosen"], stats["applied"]) == (1, 0)

    applied = client.post("/api/apply?src=youtube&dst=yandex").json()
    assert applied["applied"] == 1
    assert fake.liked == ["yt-1"], "exactly the picked track should be liked"

    stats = client.get("/api/apply/stats?src=youtube&dst=yandex").json()
    assert (stats["chosen"], stats["applied"]) == (0, 1)


def test_apply_is_idempotent(client, fake):
    client.post("/api/token/youtube", json={"value": "header-block"})
    client.post("/api/token/yandex", json={"value": "y0-token"})
    client.post("/api/import/youtube")

    playlist_id = db.get_liked_playlist("youtube")["id"]
    src_track_id = db.get_playlist_tracks(playlist_id)[0]["id"]
    client.get(f"/api/candidates/{src_track_id}?dst=yandex")
    client.post(f"/api/choose/{src_track_id}?dst=yandex", json={"external_id": "yt-1"})

    first = client.post("/api/apply?src=youtube&dst=yandex").json()
    second = client.post("/api/apply?src=youtube&dst=yandex").json()

    assert first["applied"] == 1
    assert second["applied"] == 0
    assert second["done"] is True
    assert fake.liked == ["yt-1"], "second run must not re-like anything"


def test_candidates_are_cached(client, fake, monkeypatch):
    client.post("/api/token/youtube", json={"value": "header-block"})
    client.post("/api/token/yandex", json={"value": "y0-token"})
    client.post("/api/import/youtube")

    playlist_id = db.get_liked_playlist("youtube")["id"]
    src_track_id = db.get_playlist_tracks(playlist_id)[0]["id"]

    searches = []
    original = fake.search
    monkeypatch.setattr(fake, "search", lambda q, limit=10: searches.append(q) or original(q, limit))

    client.get(f"/api/candidates/{src_track_id}?dst=yandex")
    client.get(f"/api/candidates/{src_track_id}?dst=yandex")
    assert len(searches) == 1, "second view should hit the cache"

    client.get(f"/api/candidates/{src_track_id}?dst=yandex&refresh=true")
    assert len(searches) == 2, "refresh must bypass the cache"


def test_skip_marks_track(client, fake):
    client.post("/api/token/youtube", json={"value": "header-block"})
    client.post("/api/token/yandex", json={"value": "y0-token"})
    client.post("/api/import/youtube")

    playlist_id = db.get_liked_playlist("youtube")["id"]
    src_track_id = db.get_playlist_tracks(playlist_id)[0]["id"]

    client.post(f"/api/skip/{src_track_id}?dst=yandex")

    stats = client.get("/api/apply/stats?src=youtube&dst=yandex").json()
    assert (stats["skipped"], stats["chosen"]) == (1, 0)


def test_same_service_pair_rejected(client):
    response = client.get("/api/tracks?src=youtube&dst=youtube")
    assert response.status_code == 400


def test_unknown_service_rejected(client):
    response = client.get("/api/tracks?src=spotify&dst=youtube")
    assert response.status_code == 404


def test_migrate_page_renders(client):
    response = client.get("/migrate/yandex/youtube")
    assert response.status_code == 200
    assert "Yandex Music" in response.text
