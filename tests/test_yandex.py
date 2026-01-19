from types import SimpleNamespace

from app.integrations.yandex import YandexClient


def make_album(title="Album", cover_uri="avatars.yandex.net/get-music-content/1/%%"):
    album = SimpleNamespace(title=title, cover_uri=cover_uri)

    def get_cover_url(size="200x200"):
        assert isinstance(album.cover_uri, str)
        return f"https://{album.cover_uri.replace('%%', size)}"

    album.get_cover_url = get_cover_url
    return album


def make_track(album, track_id=123, duration_ms=245_000):
    return SimpleNamespace(
        id=track_id,
        title="Blue Monday",
        artists=[SimpleNamespace(name="New Order"), SimpleNamespace(name="Guest")],
        albums=[album] if album else [],
        duration_ms=duration_ms,
    )


def test_normalizes_a_regular_track():
    track = YandexClient._normalize(make_track(make_album()))

    assert track["external_id"] == "123"
    assert track["artists"] == "New Order, Guest"
    assert track["duration_s"] == 245
    assert track["thumbnail"].endswith("200x200")


def test_album_without_cover_does_not_raise():
    track = YandexClient._normalize(make_track(make_album(cover_uri=None)))

    assert track["thumbnail"] is None
    assert track["title"] == "Blue Monday"


def test_track_without_album_does_not_raise():
    track = YandexClient._normalize(make_track(None))

    assert track["album"] is None
    assert track["thumbnail"] is None


def test_missing_duration_is_not_zero_seconds():
    track = YandexClient._normalize(make_track(make_album(), duration_ms=None))

    assert track["duration_s"] is None
