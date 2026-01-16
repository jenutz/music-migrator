from .core import session
from .models import Setting


def get_setting(key: str, default: str | None = None) -> str | None:
    with session() as db_session:
        row = db_session.get(Setting, key)
        return row.value if row else default


def set_setting(key: str, value: str) -> None:
    with session() as db_session:
        row = db_session.get(Setting, key)
        if row is None:
            db_session.add(Setting(key=key, value=value))
        else:
            row.value = value
