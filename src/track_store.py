from src.db import conn
from src.api.factory import MusicService


def save_tracks(tracks: list[dict], service: MusicService, overwrite: bool = False):
    db_name = f"tracks_{service.value}"

    if overwrite:
        conn.execute(f"DELETE FROM {db_name}")

    data_to_insert = [
        (t["id"], t["title"], t["artists"], t.get("album"), t.get("thumbnail"), t["duration_s"])
        for t in tracks
    ]

    conn.executemany(
        f"""INSERT OR REPLACE INTO {db_name} (id, title, artists, album, thumbnail, duration_s) VALUES (?, ?, ?, ?, ?, ?)""",
        data_to_insert,
    )
    conn.commit()


def load_tracks(service: MusicService) -> list[dict]:
    db_name = f"tracks_{service.value}"

    cur = conn.execute(
        f"""
        SELECT id, title, artists, album, thumbnail, duration_s FROM {db_name}
    """
    )

    rows = cur.fetchall()

    tracks = [
        {
            "id": row[0],
            "title": row[1],
            "artists": row[2],
            "album": row[3],
            "thumbnail": row[4],
            "duration_s": row[5],
        }
        for row in rows
    ]
    return tracks


def is_stored(service: MusicService) -> bool:
    table_name = f"tracks_{service.value}"
    cur = conn.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
    return cur.fetchone() is not None
