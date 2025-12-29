"""Shared test fixtures.

The database path is derived from ``DATA_DIR`` at import time, so the
environment has to be patched before any ``app`` module is imported.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP_DIR = tempfile.mkdtemp(prefix="music-migrator-tests-")
os.environ["DATA_DIR"] = _TMP_DIR

from app import db  # noqa: E402  (import after DATA_DIR is set)


@pytest.fixture(autouse=True)
def clean_database():
    """Start every test from an empty schema."""
    db.init_db()
    for table in ("matches", "search_cache", "playlist_tracks", "playlists", "tracks", "settings"):
        db._conn.execute(f"DELETE FROM {table}")  # noqa: SLF001 - test helper
    db._conn.commit()  # noqa: SLF001
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
    ids = [row["id"] for row in db.playlist_tracks(playlist_id)]
    return playlist_id, ids


@pytest.fixture
def target(imported):
    """A target playlist created by exporting the imported one to youtube."""
    src_playlist_id, track_ids = imported
    dst_playlist_id = db.create_playlist(
        "youtube", "Экспорт", source_playlist_id=src_playlist_id
    )
    return dst_playlist_id, track_ids
