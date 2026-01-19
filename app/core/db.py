from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DB_PATH
from app.models import Base

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session() -> Iterator[Session]:
    db_session = SessionLocal()
    try:
        yield db_session
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    Base.metadata.create_all(engine)
    with session() as db_session:
        _backfill(db_session)


def _backfill(db_session: Session) -> None:
    """Data fixups for databases written by earlier versions. There is no
    Alembic: schema changes get applied by hand to the one database.
    """
    db_session.execute(
        text(
            "UPDATE playlists SET delivery = 'likes'"
            " WHERE source_playlist_id IS NOT NULL AND delivery IS NULL"
        )
    )
    db_session.execute(
        text(
            "UPDATE playlists SET name = 'Library'"
            " WHERE source_playlist_id IS NULL AND name IN ('Liked tracks', 'Медиатека')"
        )
    )
    db_session.execute(
        text("UPDATE playlists SET name = 'Export' WHERE source_playlist_id IS NOT NULL AND name = 'Экспорт'")
    )
