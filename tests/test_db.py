"""Storage layer tests.

These check behaviour the app relies on (ordering, dedup, state transitions),
not that sqlite echoes back what we just wrote.
"""

import sqlite3

import pytest

from app import db


def test_upsert_track_dedupes_by_service_and_external_id(track_factory):
    track = track_factory(title="Karma Police", artists="Radiohead", external_id="123")

    first = db.upsert_track(track)
    second = db.upsert_track({**track, "title": "Karma Police (Remastered)"})
    db._conn.commit()  # noqa: SLF001

    assert first == second, "same (service, external_id) must reuse the row"
    assert db.get_track(first)["title"] == "Karma Police (Remastered)"


def test_upsert_track_keeps_services_apart(track_factory):
    yandex_id = db.upsert_track(track_factory(external_id="123", service="yandex"))
    youtube_id = db.upsert_track(track_factory(external_id="123", service="youtube"))
    db._conn.commit()  # noqa: SLF001

    assert yandex_id != youtube_id, "ids collide across services"
    assert db.get_track(yandex_id)["service"] == "yandex"
    assert db.get_track(youtube_id)["service"] == "youtube"


def test_playlist_order_survives_import(track_factory):
    titles = ["Blue Monday", "Enjoy the Silence", "Sweet Dreams"]
    tracks = [track_factory(title=t, artists="X") for t in titles]

    playlist_id = db.replace_liked_playlist("yandex", "Liked tracks", tracks)
    rows = db.get_playlist_tracks(playlist_id)

    assert [row["title"] for row in rows] == titles
    assert [row["position"] for row in rows] == [0, 1, 2]


def test_reimport_replaces_previous_library(track_factory):
    db.replace_liked_playlist("yandex", "Liked tracks", [track_factory(title="A")])
    playlist_id = db.replace_liked_playlist("yandex", "Liked tracks", [track_factory(title="C")])

    rows = db.get_playlist_tracks(playlist_id)
    assert [row["title"] for row in rows] == ["C"], "stale tracks must not linger"
    assert db.get_liked_playlist("yandex")["id"] == playlist_id


def test_reimport_does_not_leak_old_playlists(track_factory):
    first = db.replace_liked_playlist("yandex", "Liked tracks", [track_factory(title="A")])
    db.replace_liked_playlist("yandex", "Liked tracks", [track_factory(title="B")])

    assert db.get_playlist_tracks(first) == [], "old playlist should be gone"
    assert db.get_liked_playlist("yandex")["id"] != first


def test_chosen_match_moves_to_applied(playlist):
    playlist_id, track_ids = playlist

    db.save_match(
        track_ids[0],
        "youtube",
        {"external_id": "yt-1", "title": "Blue Monday", "artists": "New Order"},
        score=97,
    )
    assert db.count_pending(playlist_id, "youtube") == 1

    match = db.get_match(track_ids[0], "youtube")
    db.mark_applied(match["id"])

    counts = db.match_counts(playlist_id, "youtube")
    assert (counts["chosen"], counts["applied"], counts["total"]) == (0, 1, 3)
    assert db.count_pending(playlist_id, "youtube") == 0


def test_skip_overrides_previous_choice(playlist):
    _, track_ids = playlist
    src = track_ids[0]

    db.save_match(src, "youtube", {"external_id": "yt-1", "title": "X"}, score=50)
    db.skip_match(src, "youtube")

    match = db.get_match(src, "youtube")
    assert match["status"] == "skipped"
    assert match["dst_external_id"] is None, "skipped tracks must not be applied later"


def test_matches_are_scoped_per_destination(playlist):
    _, track_ids = playlist
    src = track_ids[0]

    db.save_match(src, "youtube", {"external_id": "yt-1", "title": "X"}, score=50)
    db.skip_match(src, "yandex")

    assert db.get_match(src, "youtube")["status"] == "chosen"
    assert db.get_match(src, "yandex")["status"] == "skipped"


def test_ordered_matches_tracks_unreviewed_rows(playlist):
    playlist_id, track_ids = playlist
    db.save_match(track_ids[1], "youtube", {"external_id": "yt-2", "title": "Enjoy"}, score=80)

    rows = db.ordered_matches(playlist_id, "youtube")

    assert [row["position"] for row in rows] == [0, 1, 2]
    assert [row["status"] for row in rows] == [None, "chosen", None]


def test_deleting_playlist_cascades_to_rows(track_factory):
    playlist_id = db.replace_liked_playlist(
        "yandex", "Liked tracks", [track_factory(title="A"), track_factory(title="B")]
    )

    db._conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))  # noqa: SLF001
    db._conn.commit()  # noqa: SLF001

    assert db.get_playlist_tracks(playlist_id) == []


def test_deleting_unreferenced_track_cascades_to_matches(track_factory):
    track_id = db.upsert_track(track_factory(title="Orphan", external_id="orphan-1"))
    db._conn.commit()  # noqa: SLF001
    db.save_match(track_id, "youtube", {"external_id": "yt-9", "title": "Orphan"}, score=40)

    db._conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))  # noqa: SLF001
    db._conn.commit()  # noqa: SLF001

    assert db.get_match(track_id, "youtube") is None


def test_track_used_by_playlist_cannot_be_deleted(playlist):
    _, track_ids = playlist

    with pytest.raises(sqlite3.IntegrityError):
        db._conn.execute("DELETE FROM tracks WHERE id = ?", (track_ids[0],))  # noqa: SLF001


def test_search_cache_expires_on_refresh(playlist):
    _, track_ids = playlist
    payload = [{"external_id": "a", "score": 10}]

    db.set_cached_search(track_ids[0], "youtube", payload)
    assert db.get_cached_search(track_ids[0], "youtube") == payload

    db.clear_cached_search("youtube")
    assert db.get_cached_search(track_ids[0], "youtube") is None


def test_match_survives_reimport_of_same_library(playlist):
    playlist_id, track_ids = playlist
    src = track_ids[0]
    db.save_match(src, "youtube", {"external_id": "yt-1", "title": "X"}, score=50)

    db.replace_liked_playlist(
        "yandex",
        "Liked tracks",
        [
            {"service": "yandex", "external_id": db.get_track(t)["external_id"],
             "title": db.get_track(t)["title"], "artists": db.get_track(t)["artists"],
             "album": None, "thumbnail": None, "duration_s": 200}
            for t in track_ids
        ],
    )

    assert db.get_match(src, "youtube")["status"] == "chosen", "re-import must not lose review work"
