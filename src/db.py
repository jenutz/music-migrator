import sqlite3
from src.api.factory import MusicService

conn = sqlite3.connect("app.db", check_same_thread=False)

conn.execute(
    """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""
)

for service in MusicService:
    conn.execute(
        f"""
    CREATE TABLE IF NOT EXISTS tracks_{service.value} (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        artists TEXT,
        album TEXT,
        thumbnail TEXT,
        duration_s INTEGER
    )
    """
    )

conn.commit()
