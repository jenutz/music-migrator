import pytest

from app.integrations.youtube import strip_tags
from app.services.match_service import score_track


def source(title="Blue Monday", artists="New Order", duration_s=450):
    return {"title": title, "artists": artists, "duration_s": duration_s}


def candidate(title, artists, duration_s=450, result_type="song"):
    return {
        "title": title,
        "artists": artists,
        "duration_s": duration_s,
        "result_type": result_type,
    }


@pytest.mark.parametrize(
    "other",
    [
        candidate("Blue Monday", "New Order"),
        candidate("Blue Monday (Remastered 2015)", "New Order"),
        candidate("Blue Monday - Official Video", "New Order"),
        candidate("blue monday", "new order"),
    ],
)
def test_same_recording_scores_high(other):
    assert score_track(source(), other) >= 85


def test_different_song_scores_low():
    assert score_track(source(), candidate("Sweet Dreams", "Eurythmics")) < 55


def test_cover_with_other_artist_scores_lower_than_original():
    original = score_track(source(), candidate("Blue Monday", "New Order"))
    cover = score_track(source(), candidate("Blue Monday", "Orkestra Obsolete"))
    assert cover < original


def test_large_duration_mismatch_penalised():
    exact = score_track(source(), candidate("Blue Monday", "New Order", duration_s=450))
    live = score_track(source(), candidate("Blue Monday", "New Order", duration_s=900))
    assert live < exact


def test_music_videos_rank_below_songs():
    song = score_track(source(), candidate("Blue Monday", "New Order", result_type="song"))
    video = score_track(source(), candidate("Blue Monday", "New Order", result_type="video"))
    assert video < song


def test_score_is_bounded():
    assert 0 <= score_track(source(), candidate("", "")) <= 100


def test_missing_metadata_does_not_crash():
    assert score_track({"title": "X", "artists": "", "duration_s": None}, candidate("X", "")) >= 0


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Blue Monday (Official Video)", "Blue Monday"),
        ("Creep (Remastered 2011)", "Creep"),
        ("Teardrop [HD]", "Teardrop"),
        ("Yesterday (Lyrics)", "Yesterday"),
    ],
)
def test_strip_tags(raw, expected):
    assert strip_tags(raw).strip() == expected
