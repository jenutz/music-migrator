"""Candidate search: cached answers, local-first matching, choosing one."""

from app import db


def _target(client, src_playlist_id=1):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    return client.post(
        f"/api/export/{src_playlist_id}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]


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


# --- local-first search ---------------------------------------------------


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


def test_a_db_answer_can_be_chosen_without_a_cached_search(client, fake, youtube_import):
    """Local candidates are not cached, so choosing one has to work anyway."""
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
        f"/api/candidates/{src_track_id}?playlist_id={target_id}"
    ).json()["candidates"]
    assert db.get_cached_search(src_track_id, "yandex") is None

    response = client.post(
        f"/api/choose/{src_track_id}?playlist_id={target_id}",
        json={"external_id": candidates[0]["external_id"]},
    )

    assert response.status_code == 200
    assert client.get(f"/api/playlist/{target_id}").json()["playlist"]["chosen"] == 1
