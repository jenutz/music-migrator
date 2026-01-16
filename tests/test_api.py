from app import db


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Music Migrator" in response.text


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
