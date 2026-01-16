"""Reviewing a target playlist and sending the chosen tracks."""


def test_full_flow(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex", "delivery": "likes"}
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
    assert applied["sent"] == 1
    assert fake.liked == ["yt-1"], "exactly the picked track should be liked"

    stats = client.get(f"/api/apply/stats?playlist_id={target_id}").json()
    assert (stats["chosen"], stats["applied"]) == (0, 1)


def test_apply_is_idempotent(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex", "delivery": "likes"}
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


def test_skip_marks_track(client, fake, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]
    src_track_id = client.get(f"/api/tracks?playlist_id={target_id}").json()["tracks"][0]["src_track_id"]

    client.post(f"/api/skip/{src_track_id}?playlist_id={target_id}")

    stats = client.get(f"/api/apply/stats?playlist_id={target_id}").json()
    assert (stats["skipped"], stats["chosen"]) == (1, 0)
