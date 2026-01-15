"""SQLite data layer, split by subject.

Kept as a package purely for reading order - call sites still do
``db.get_playlist(...)``, because everything is re-exported here.
"""

from .cache import clear_cached_search, get_cached_search, set_cached_search
from .core import (
    DB_PATH,
    DATA_DIR,
    SCHEMA,
    _conn,
    _lock,
    init_db,
    now,
    query,
    query_one,
)
from .matches import (
    clear_matches,
    count_pending,
    get_match,
    mark_applied,
    match_counts,
    ordered_matches,
    pending_batch,
    save_match,
    skip_match,
)
from .playlists import (
    create_playlist,
    delete_playlist,
    get_playlist,
    list_playlists,
    playlist_counts,
    playlist_kind,
    playlist_track_count,
    playlist_tracks,
    set_remote_playlist,
)
from .settings import get_setting, set_setting
from .tracks import get_track, tracks_for_service, upsert_track

__all__ = [
    "DB_PATH",
    "_conn",
    "_lock",
    "DATA_DIR",
    "SCHEMA",
    "clear_cached_search",
    "clear_matches",
    "count_pending",
    "create_playlist",
    "delete_playlist",
    "get_cached_search",
    "get_match",
    "get_playlist",
    "get_setting",
    "get_track",
    "init_db",
    "list_playlists",
    "mark_applied",
    "match_counts",
    "now",
    "ordered_matches",
    "pending_batch",
    "playlist_counts",
    "playlist_kind",
    "playlist_track_count",
    "playlist_tracks",
    "query",
    "query_one",
    "save_match",
    "set_cached_search",
    "set_remote_playlist",
    "set_setting",
    "skip_match",
    "tracks_for_service",
    "upsert_track",
]
