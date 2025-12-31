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


@pytest.fixture
def youtube_import(client, fake):
    """Log in to youtube and import, returning the new playlist id."""
    client.post("/api/token/youtube", json={"value": "header-block"})
    response = client.post("/api/import/youtube")
    return response.json()["playlist_id"]


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


def test_import_creates_a_playlist(client, fake):
    client.post("/api/token/youtube", json={"value": "header-block"})
    response = client.post("/api/import/youtube")

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1

    playlist = db.get_playlist(body["playlist_id"])
    assert playlist["service"] == "youtube"
    assert playlist["source_playlist_id"] is None
    assert db.playlist_tracks(playlist["id"])[0]["title"] == "Blue Monday"


def test_each_import_is_a_separate_playlist(client, fake):
    client.post("/api/token/youtube", json={"value": "header-block"})

    first = client.post("/api/import/youtube").json()["playlist_id"]
    second = client.post("/api/import/youtube").json()["playlist_id"]

    assert first != second
    listed = client.get("/api/playlists").json()["playlists"]
    assert {playlist["id"] for playlist in listed} == {first, second}


def test_export_creates_a_target_playlist(client, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})

    response = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    )

    assert response.status_code == 200
    target = response.json()["playlist"]
    assert target["service"] == "yandex"
    assert target["kind"] == "target"
    assert target["source_playlist_id"] == youtube_import
    assert target["total"] == 1


def test_export_needs_a_token_on_the_destination(client, youtube_import):
    response = client.post(f"/api/export/{youtube_import}", json={"dst_service": "yandex"})

    assert response.status_code == 400
    assert "войдите" in response.json()["detail"].lower()


def test_export_rejects_same_service(client, youtube_import):
    response = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "youtube"}
    )
    assert response.status_code == 400


def test_cannot_export_an_export(client, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]

    response = client.post(f"/api/export/{target_id}", json={"dst_service": "youtube"})
    assert response.status_code == 400


def test_migrate_page_opens_the_target_playlist(client, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]

    response = client.get(f"/migrate/{target_id}")
    assert response.status_code == 200
    assert "YouTube Music" in response.text


def test_migrate_page_rejects_an_imported_playlist(client, youtube_import):
    assert client.get(f"/migrate/{youtube_import}").status_code == 400


def test_full_flow(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]

    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    # candidates are ranked, best first -- the live-only video must lose
    candidates = client.get(
        f"/api/candidates/{src_track_id}?playlist_id={target_id}"
    ).json()["candidates"]
    assert [c["external_id"] for c in candidates] == ["yt-1", "yt-2"]
    assert candidates[0]["score"] > candidates[1]["score"]

    chosen = client.post(
        f"/api/choose/{src_track_id}?playlist_id={target_id}",
        json={"external_id": "yt-1"},
    )
    assert chosen.status_code == 200

    stats = client.get(f"/api/apply/stats?playlist_id={target_id}").json()
    assert (stats["chosen"], stats["applied"]) == (1, 0)

    applied = client.post(f"/api/apply?playlist_id={target_id}").json()
    assert applied["applied"] == 1
    assert fake.liked == ["yt-1"], "exactly the picked track should be liked"

    stats = client.get(f"/api/apply/stats?playlist_id={target_id}").json()
    assert (stats["chosen"], stats["applied"]) == (0, 1)


def test_apply_is_idempotent(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    client.get(f"/api/candidates/{src_track_id}?playlist_id={target_id}")
    client.post(
        f"/api/choose/{src_track_id}?playlist_id={target_id}",
        json={"external_id": "yt-1"},
    )

    first = client.post(f"/api/apply?playlist_id={target_id}").json()
    second = client.post(f"/api/apply?playlist_id={target_id}").json()

    assert first["applied"] == 1
    assert second["applied"] == 0
    assert second["done"] is True
    assert fake.liked == ["yt-1"], "second run must not re-like anything"


def test_two_exports_do_not_share_choices(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    first = client.post(f"/api/export/{youtube_import}", json={"dst_service": "yandex"}).json()["playlist_id"]
    second = client.post(f"/api/export/{youtube_import}", json={"dst_service": "yandex"}).json()["playlist_id"]

    src_track_id = client.get(f"/api/tracks?playlist_id={first}").json()["tracks"][0]["src_track_id"]
    client.get(f"/api/candidates/{src_track_id}?playlist_id={first}")
    client.post(f"/api/choose/{src_track_id}?playlist_id={first}", json={"external_id": "yt-1"})

    assert client.get(f"/api/apply/stats?playlist_id={first}").json()["chosen"] == 1
    assert client.get(f"/api/apply/stats?playlist_id={second}").json()["chosen"] == 0


def test_candidates_are_cached(client, fake, monkeypatch, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    searches = []
    original = fake.search
    monkeypatch.setattr(fake, "search", lambda q, limit=10: searches.append(q) or original(q, limit))

    client.get(f"/api/candidates/{src_track_id}?playlist_id={target_id}")
    client.get(f"/api/candidates/{src_track_id}?playlist_id={target_id}")
    assert len(searches) == 1, "second view should hit the cache"

    client.get(f"/api/candidates/{src_track_id}?playlist_id={target_id}&refresh=true")
    assert len(searches) == 2, "refresh must bypass the cache"


def test_skip_marks_track(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    client.post(f"/api/skip/{src_track_id}?playlist_id={target_id}")

    stats = client.get(f"/api/apply/stats?playlist_id={target_id}").json()
    assert (stats["skipped"], stats["chosen"]) == (1, 0)


def test_playlist_detail_lists_tracks(client, youtube_import):
    body = client.get(f"/api/playlist/{youtube_import}").json()

    assert body["playlist"]["kind"] == "imported"
    assert [track["title"] for track in body["tracks"]] == ["Blue Monday"]


def test_playlist_detail_of_a_target_shows_statuses(client, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]

    body = client.get(f"/api/playlist/{target_id}").json()

    assert body["playlist"]["kind"] == "target"
    assert body["tracks"][0]["src_title"] == "Blue Monday"
    assert body["tracks"][0]["status"] is None


def test_deleting_a_playlist_removes_it_from_the_list(client, youtube_import):
    assert client.delete(f"/api/playlist/{youtube_import}").status_code == 200
    assert client.get("/api/playlists").json()["playlists"] == []


def test_unknown_playlist_is_404(client):
    assert client.get("/api/playlist/9999").status_code == 404
    assert client.get("/api/tracks?playlist_id=9999").status_code == 404


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


# --- yandex device flow endpoints ----------------------------------------


def test_device_flow_status_starts_idle(client):
    from app.main import yandex_auth

    yandex_auth.reset()
    response = client.get("/api/auth/yandex/status")

    assert response.status_code == 200
    assert response.json()["state"] == "idle"


def test_device_flow_start_exposes_the_user_code(client, monkeypatch):
    from app.services.auth_service import YandexDeviceAuth
    from tests.test_auth import StubOAuthClient, token, wait_for

    manager = YandexDeviceAuth(lambda: StubOAuthClient(token=token()))
    monkeypatch.setattr("app.main.yandex_auth", manager)

    started = client.post("/api/auth/yandex/start")
    assert started.status_code == 200

    wait_for(manager, "success")
    response = client.get("/api/auth/yandex/status")

    assert response.json()["state"] == "success"
    assert db.get_setting("token-yandex") == "yandex-access"


def test_device_flow_can_be_cancelled(client, monkeypatch):
    from app.services.auth_service import YandexDeviceAuth
    from tests.test_auth import BlockingOAuthClient, wait_for

    manager = YandexDeviceAuth(lambda: BlockingOAuthClient())
    monkeypatch.setattr("app.main.yandex_auth", manager)

    client.post("/api/auth/yandex/start")
    wait_for(manager, "pending")

    response = client.post("/api/auth/yandex/cancel")
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


# --- local-first search ---------------------------------------------------


def _target(client, src_playlist_id=1):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    return client.post(
        f"/api/export/{src_playlist_id}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]


def test_known_track_is_matched_from_the_database_without_a_request(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    db.create_playlist(
        "yandex",
        "Медиатека",
        [{
            "service": "yandex",
            "external_id": "ya-blue-monday",
            "title": "Blue Monday",
            "artists": "New Order",
            "album": "Substance",
            "thumbnail": None,
            "duration_s": 450,
        }],
    )

    target_id = _target(client, youtube_import)
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    calls = []
    original = fake.search
    fake.search = lambda q, limit=10: calls.append(q) or original(q, limit)

    candidates = client.get(
        f"/api/candidates/{src_track_id}?playlist_id={target_id}"
    ).json()["candidates"]

    assert calls == [], "a confident local match must not hit the API"
    assert candidates[0]["external_id"] == "ya-blue-monday"
    assert candidates[0]["origin"] == "db"


def test_unknown_track_still_asks_the_service(client, fake, youtube_import):
    target_id = _target(client, youtube_import)
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    calls = []
    original = fake.search
    fake.search = lambda q, limit=10: calls.append(q) or original(q, limit)

    candidates = client.get(
        f"/api/candidates/{src_track_id}?playlist_id={target_id}"
    ).json()["candidates"]

    assert len(calls) == 1, "empty local library means we have to ask"
    assert candidates[0]["origin"] == "search"


def test_local_hits_are_merged_with_remote_ones(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    db.create_playlist(
        "yandex",
        "Медиатека",
        [{
            "service": "yandex",
            "external_id": "ya-live",
            "title": "Blue Monday (Live at the BBC)",
            "artists": "New Order",
            "album": None,
            "thumbnail": None,
            "duration_s": 900,
        }],
    )

    target_id = _target(client, youtube_import)
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    candidates = client.get(
        f"/api/candidates/{src_track_id}?playlist_id={target_id}"
    ).json()["candidates"]
    ids = [c["external_id"] for c in candidates]

    assert "yt-1" in ids, "remote results are not dropped"
    assert "ya-live" in ids, "a weaker local hit still shows up alongside them"
    assert ids[0] == "yt-1", "the better match stays on top"


def test_same_recording_is_not_listed_twice(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    db.create_playlist(
        "yandex",
        "Медиатека",
        [{
            "service": "yandex",
            "external_id": "yt-1",  # same id the fake service returns
            "title": "Blue Monday",
            "artists": "New Order",
            "album": None,
            "thumbnail": None,
            "duration_s": 450,
        }],
    )

    target_id = _target(client, youtube_import)
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    candidates = client.get(
        f"/api/candidates/{src_track_id}?playlist_id={target_id}"
    ).json()["candidates"]

    assert [c["external_id"] for c in candidates].count("yt-1") == 1


def test_refresh_forces_a_real_search(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    db.create_playlist(
        "yandex",
        "Медиатека",
        [{
            "service": "yandex",
            "external_id": "ya-blue-monday",
            "title": "Blue Monday",
            "artists": "New Order",
            "album": None,
            "thumbnail": None,
            "duration_s": 450,
        }],
    )

    target_id = _target(client, youtube_import)
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    calls = []
    original = fake.search
    fake.search = lambda q, limit=10: calls.append(q) or original(q, limit)

    client.get(f"/api/candidates/{src_track_id}?playlist_id={target_id}&refresh=true")

    assert len(calls) == 1, "refresh is the user asking for fresh results"


def test_custom_query_ignores_the_local_library(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    db.create_playlist(
        "yandex",
        "Медиатека",
        [{
            "service": "yandex",
            "external_id": "ya-blue-monday",
            "title": "Blue Monday",
            "artists": "New Order",
            "album": None,
            "thumbnail": None,
            "duration_s": 450,
        }],
    )

    target_id = _target(client, youtube_import)
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    candidates = client.get(
        f"/api/candidates/{src_track_id}?playlist_id={target_id}&query=new+order+blue"
    ).json()["candidates"]

    assert candidates[0]["origin"] == "search"


def test_a_strong_local_match_does_not_drag_noise_along(client, fake, youtube_import):
    """Near misses score 50-70 against the whole library; a perfect hit drops them."""
    client.post("/api/token/yandex", json={"value": "y0-token"})
    db.create_playlist(
        "yandex",
        "Медиатека",
        [
            {
                "service": "yandex",
                "external_id": "ya-blue-monday",
                "title": "Blue Monday",
                "artists": "New Order",
                "album": "Power, Corruption & Lies",
                "thumbnail": None,
                "duration_s": 450,
            },
            {
                # scores 70: similar title, wrong artist
                "service": "yandex",
                "external_id": "ya-remastered",
                "title": "Blue Monday (Remastered)",
                "artists": "Various Artists",
                "album": None,
                "thumbnail": None,
                "duration_s": 450,
            },
            {
                # scores 50: same title, wrong artist, wrong length
                "service": "yandex",
                "external_id": "ya-live",
                "title": "Blue Monday (Live)",
                "artists": "Somebody Else",
                "album": None,
                "thumbnail": None,
                "duration_s": 900,
            },
        ],
    )

    target_id = _target(client, youtube_import)
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    candidates = client.get(
        f"/api/candidates/{src_track_id}?playlist_id={target_id}"
    ).json()["candidates"]

    assert [c["title"] for c in candidates] == ["Blue Monday"]


def test_local_answers_are_not_cached(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    db.create_playlist(
        "yandex",
        "Медиатека",
        [{
            "service": "yandex",
            "external_id": "ya-blue-monday",
            "title": "Blue Monday",
            "artists": "New Order",
            "album": None,
            "thumbnail": None,
            "duration_s": 450,
        }],
    )

    target_id = _target(client, youtube_import)
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    client.get(f"/api/candidates/{src_track_id}?playlist_id={target_id}")

    assert db.get_cached_search(src_track_id, "yandex") is None
