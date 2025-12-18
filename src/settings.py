from src.db import conn
import threading

_lock = threading.Lock()


def set(key: str, value: str):
    with _lock:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def get(key: str, default=None):
    cur = conn.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else default
