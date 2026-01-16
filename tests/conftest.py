"""Shared test fixtures.

The database path is derived from ``DATA_DIR`` at import time, so the
environment has to be patched before any ``app`` module is imported.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP_DIR = tempfile.mkdtemp(prefix="music-migrator-tests-")
os.environ["DATA_DIR"] = _TMP_DIR

from app import db  # noqa: E402  (import after DATA_DIR is set)
from app.integrations.factory import reset_cache  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    db.init_db()
    # child rows first, or the foreign keys complain
    with db.session() as db_session:
        for model in (db.Match, db.SearchCache, db.PlaylistTrack, db.Playlist, db.Track, db.Setting):
            db_session.execute(delete(model))
    yield


@pytest.fixture
def track_factory():
    def _make(title="Song", artists="Artist", service="yandex", external_id=None, duration_s=200):
        return {
            "service": service,
            "external_id": external_id or f"{title}-{artists}".lower().replace(" ", "-"),
            "title": title,
            "artists": artists,
            "album": "Album",
            "thumbnail": None,
            "duration_s": duration_s,
        }

    return _make


@pytest.fixture
def imported(track_factory):
    """An imported playlist and the local ids of its tracks, in order."""
    tracks = [
        track_factory(title="Blue Monday", artists="New Order"),
        track_factory(title="Enjoy the Silence", artists="Depeche Mode"),
        track_factory(title="Sweet Dreams", artists="Eurythmics"),
    ]
    playlist_id = db.create_playlist("yandex", "Медиатека", tracks)
    ids = [entry.track_id for entry in db.playlist_tracks(playlist_id)]
    return playlist_id, ids


@pytest.fixture
def target(imported):
    """A target playlist created by exporting the imported one to youtube."""
    src_playlist_id, track_ids = imported
    dst_playlist_id = db.create_playlist(
        "youtube", "Экспорт", source_playlist_id=src_playlist_id
    )
    return dst_playlist_id, track_ids


class FakeClient:
    def __init__(self, results=None):
        self.results = results or []
        self.liked = []
        self.unliked = []
        self.created = []
        self.added = []

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
        self.unliked.extend(ids)
        return len(ids)

    def create_playlist(self, name, track_ids=()):
        self.created.append({"name": name, "tracks": list(track_ids)})
        return f"fake-playlist-{len(self.created)}"

    def add_playlist_tracks(self, playlist_id, track_ids):
        self.added.append({"playlist_id": playlist_id, "tracks": list(track_ids)})
        return len(list(track_ids))


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
