"""Where applied tracks land, and emptying a service's likes."""

from app import db


def test_playlist_delivery_builds_one_playlist_and_appends_to_it(client, fake, imported):
    src_id, track_ids = imported
    client.post("/api/token/youtube", json={"value": "header-block"})
    target_id = client.post(
        f"/api/export/{src_id}", json={"dst_service": "youtube", "delivery": "playlist"}
    ).json()["playlist_id"]

    for track_id in track_ids:
        db.save_match(target_id, track_id, {"external_id": f"yt-{track_id}", "title": "X"}, 90)

    first = client.post(f"/api/apply?playlist_id={target_id}&limit=2").json()
    assert first["applied"] == 2
    assert first["sent"] == 2
    assert len(fake.created) == 1
    assert fake.created[0]["tracks"] == [f"yt-{t}" for t in track_ids[:2]]
    assert fake.created[0]["name"] == "Медиатека", "the playlist keeps the source name"
    assert fake.liked == [], "playlist delivery must not like anything"

    remote = client.get(f"/api/playlist/{target_id}").json()["playlist"]
    assert remote["remote_playlist_id"] == "fake-playlist-1"

    second = client.post(f"/api/apply?playlist_id={target_id}&limit=2").json()
    assert second["applied"] == 1
    assert len(fake.created) == 1, "a second batch appends instead of starting a new playlist"
    assert fake.added == [{"playlist_id": "fake-playlist-1", "tracks": [f"yt-{track_ids[2]}"]}]


def test_likes_delivery_never_creates_a_playlist(client, fake, imported):
    src_id, track_ids = imported
    client.post("/api/token/youtube", json={"value": "header-block"})
    target_id = client.post(
        f"/api/export/{src_id}", json={"dst_service": "youtube", "delivery": "likes"}
    ).json()["playlist_id"]

    db.save_match(target_id, track_ids[0], {"external_id": "yt-a", "title": "X"}, 90)
    client.post(f"/api/apply?playlist_id={target_id}")

    assert fake.liked == ["yt-a"]
    assert fake.created == []


# --- clearing a service's likes -------------------------------------------


def test_clear_likes_empties_the_service(client, fake, monkeypatch):
    monkeypatch.setattr("app.services.library_service.choose_api", lambda *a, **k: fake)
    client.post("/api/token/youtube", json={"value": "header-block"})

    response = client.post("/api/service/youtube/clear-likes")

    assert response.json()["removed"] == 1
    assert fake.unliked == ["yt-blue-monday"]


def test_clear_likes_needs_a_token(client):
    response = client.post("/api/service/youtube/clear-likes")
    assert response.status_code == 400
    assert "войдите" in response.json()["detail"].lower()
