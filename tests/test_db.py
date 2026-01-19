import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app import crud
from app.core.db import init_db, session
from app.models import Playlist, Track


def test_upsert_track_dedupes_by_service_and_external_id(track_factory):
    track = track_factory(title="Karma Police", artists="Radiohead", external_id="123")

    first = crud.upsert_track(track)
    second = crud.upsert_track({**track, "title": "Karma Police (Remastered)"})

    assert first == second, "same (service, external_id) must reuse the row"
    assert crud.get_track(first).title == "Karma Police (Remastered)"


def test_upsert_track_keeps_services_apart(track_factory):
    yandex_id = crud.upsert_track(track_factory(external_id="123", service="yandex"))
    youtube_id = crud.upsert_track(track_factory(external_id="123", service="youtube"))

    assert yandex_id != youtube_id, "ids collide across services"
    assert crud.get_track(yandex_id).service == "yandex"
    assert crud.get_track(youtube_id).service == "youtube"


def test_playlist_order_survives_import(track_factory):
    titles = ["Blue Monday", "Enjoy the Silence", "Sweet Dreams"]
    tracks = [track_factory(title=t, artists="X") for t in titles]

    playlist_id = crud.create_playlist("yandex", "Library", tracks)
    rows = crud.playlist_tracks(playlist_id)

    assert [entry.track.title for entry in rows] == titles
    assert [entry.position for entry in rows] == [0, 1, 2]


def test_importing_twice_keeps_both_snapshots(imported, track_factory):
    first_id, _ = imported

    second_id = crud.create_playlist(
        "yandex", "Library", [track_factory(title="Something New")]
    )

    assert first_id != second_id
    assert len(crud.list_playlists("yandex")) == 2
    assert crud.playlist_track_count(first_id) == 3, "the old snapshot must survive"


def test_target_playlist_is_empty_but_shares_the_source_order(imported):
    src_id, _ = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)

    assert crud.playlist_track_count(dst_id) == 0, "targets hold matches, not copies"
    assert crud.match_counts(src_id, dst_id)["total"] == 3


def test_playlist_kind_tells_import_from_export(imported):
    src_id, _ = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)

    assert crud.playlist_kind(crud.get_playlist(src_id)) == "imported"
    assert crud.playlist_kind(crud.get_playlist(dst_id)) == "target"


def test_chosen_match_moves_to_applied(imported):
    src_id, track_ids = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)

    crud.save_match(
        dst_id,
        track_ids[0],
        {"external_id": "yt-1", "title": "Blue Monday", "artists": "New Order"},
        score=97,
    )
    assert crud.count_pending(src_id, dst_id) == 1

    match = crud.get_match(dst_id, track_ids[0])
    crud.mark_applied(match.id)

    counts = crud.match_counts(src_id, dst_id)
    assert (counts["chosen"], counts["applied"], counts["total"]) == (0, 1, 3)
    assert crud.count_pending(src_id, dst_id) == 0


def test_skip_overrides_previous_choice(imported):
    src_id, track_ids = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)
    src = track_ids[0]

    crud.save_match(dst_id, src, {"external_id": "yt-1", "title": "X"}, score=50)
    crud.skip_match(dst_id, src)

    match = crud.get_match(dst_id, src)
    assert match.status == "skipped"
    assert match.dst_external_id is None, "skipped tracks must not be applied later"


def test_matches_are_scoped_per_target_playlist(imported):
    src_id, track_ids = imported
    first = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)
    second = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)

    crud.save_match(first, track_ids[0], {"external_id": "yt-1", "title": "X"}, score=50)
    crud.skip_match(second, track_ids[0])

    assert crud.get_match(first, track_ids[0]).status == "chosen"
    assert crud.get_match(second, track_ids[0]).status == "skipped"

    assert crud.match_counts(src_id, first)["chosen"] == 1
    assert crud.match_counts(src_id, second)["skipped"] == 1


def test_ordered_matches_tracks_unreviewed_rows(imported):
    src_id, track_ids = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)
    crud.save_match(dst_id, track_ids[1], {"external_id": "yt-2", "title": "Enjoy"}, score=80)

    rows = crud.ordered_matches(src_id, dst_id)

    assert [row["position"] for row in rows] == [0, 1, 2]
    assert [row["status"] for row in rows] == [None, "chosen", None]


def test_deleting_playlist_cascades_to_its_tracks(track_factory):
    playlist_id = crud.create_playlist(
        "yandex", "Library", [track_factory(title="A"), track_factory(title="B")]
    )

    crud.delete_playlist(playlist_id)

    assert crud.playlist_tracks(playlist_id) == []


def test_deleting_source_playlist_removes_its_exports(imported):
    src_id, _ = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)

    crud.delete_playlist(src_id)

    assert crud.get_playlist(dst_id) is None, "an export cannot outlive its source"


def test_deleting_target_playlist_keeps_the_source(imported):
    src_id, _ = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)

    crud.delete_playlist(dst_id)

    assert crud.get_playlist(src_id) is not None
    assert crud.playlist_track_count(src_id) == 3


def test_deleting_unreferenced_track_cascades_to_matches(track_factory):
    src_id = crud.create_playlist("yandex", "Library", [])
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)
    track_id = crud.upsert_track(track_factory(title="Orphan", external_id="orphan-1"))
    crud.save_match(dst_id, track_id, {"external_id": "yt-9", "title": "Orphan"}, score=40)

    with session() as db_session:
        db_session.execute(delete(Track).where(Track.id == track_id))

    assert crud.get_match(dst_id, track_id) is None


def test_track_used_by_playlist_cannot_be_deleted(imported):
    _, track_ids = imported

    with pytest.raises(IntegrityError):
        with session() as db_session:
            db_session.execute(delete(Track).where(Track.id == track_ids[0]))


def test_search_cache_expires_on_refresh(imported):
    _, track_ids = imported
    payload = [{"external_id": "a", "score": 10}]

    crud.set_cached_search(track_ids[0], "youtube", payload)
    assert crud.get_cached_search(track_ids[0], "youtube") == payload

    crud.clear_cached_search("youtube")
    assert crud.get_cached_search(track_ids[0], "youtube") is None


def test_playlist_counts_work_for_both_kinds(imported):
    src_id, track_ids = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)
    crud.save_match(dst_id, track_ids[0], {"external_id": "yt-1", "title": "X"}, score=50)

    source_counts = crud.playlist_counts(crud.get_playlist(src_id))
    target_counts = crud.playlist_counts(crud.get_playlist(dst_id))

    assert source_counts["total"] == 3
    assert (target_counts["total"], target_counts["chosen"]) == (3, 1)


def test_list_playlists_is_newest_first(imported, track_factory):
    first_id, _ = imported
    second_id = crud.create_playlist("yandex", "Library", [track_factory(title="Later")])

    ids = [playlist.id for playlist in crud.list_playlists("yandex")]
    assert ids[0] == second_id
    assert first_id in ids


def test_pending_batch_keeps_source_order(imported):
    src_id, track_ids = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)

    for track_id in reversed(track_ids):
        crud.save_match(dst_id, track_id, {"external_id": f"yt-{track_id}", "title": "X"}, score=90)

    batch = crud.pending_batch(src_id, dst_id, 10)

    assert [row["position"] for row in batch] == [0, 1, 2]
    assert [row["dst_external_id"] for row in batch] == [f"yt-{t}" for t in track_ids]


def test_delivery_defaults_to_likes_for_old_targets(imported):
    src_id, _ = imported
    dst_id = crud.create_playlist("youtube", "Export", source_playlist_id=src_id)

    with session() as db_session:
        db_session.execute(
            update(Playlist).where(Playlist.id == dst_id).values(delivery=None)
        )
    init_db()

    assert crud.get_playlist(dst_id).delivery == "likes"


def test_remote_playlist_id_is_remembered(imported):
    src_id, _ = imported
    dst_id = crud.create_playlist(
        "youtube", "Export", source_playlist_id=src_id, delivery="playlist"
    )

    assert crud.get_playlist(dst_id).remote_playlist_id is None

    crud.set_remote_playlist(dst_id, "PL123")

    assert crud.get_playlist(dst_id).remote_playlist_id == "PL123"
