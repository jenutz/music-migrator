"""Yandex OAuth Device Flow.

``yandex-music`` can fetch its own OAuth token: it prints a short user code,
waits until that code is confirmed on the Yandex page, and returns an
``OAuthToken``. The call blocks until the user confirms (or the flow times out),
so it runs in a daemon thread and the browser polls for the result.

The library never persists the token, so we do it: the access token goes into
the ``settings`` table under the same key the manual paste path uses, which
means the rest of the app does not care where the token came from.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

import yandex_music

from app import db
from app.integrations import reset_cache

logger = logging.getLogger(__name__)

SERVICE = "yandex"

# Shown on the Yandex confirmation page. Helps the user tell devices apart.
DEVICE_NAME = "Music Migrator"

# The server picks the real lifetime (usually ~5 minutes). Keep a matching cap
# so a forgotten tab does not leave a polling thread around for a whole hour.
FLOW_TIMEOUT_S = 300

TOKEN_KEY = f"token-{SERVICE}"
REFRESH_KEY = "yandex-refresh-token"
EXPIRES_KEY = "yandex-token-expires-at"


def _describe(exc: Exception) -> str:
    """Short, user-facing reason instead of a wall of library internals."""
    text = str(exc).strip() or exc.__class__.__name__

    if "Network is unreachable" in text or "Connection" in text:
        return "Нет связи с api.music.yandex.net. Проверьте сеть или вставьте токен вручную."
    if "timed out" in text:
        return "Код устарел — начните вход заново."
    if "cancelled" in text:
        return ""
    return text[:300]


class YandexDeviceAuth:
    """State machine behind the "Войти через Яндекс" button."""

    def __init__(self, client_factory: Callable[[], "yandex_music.Client"] | None = None):
        self._client_factory = client_factory or yandex_music.Client
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = self._idle()

    # --- state ------------------------------------------------------------

    @staticmethod
    def _idle() -> dict:
        return {
            "service": SERVICE,
            "state": "idle",
            "user_code": None,
            "verification_url": None,
            "expires_in": None,
            "error": None,
        }

    def _update(self, **changes) -> dict:
        with self._lock:
            self._state.update(changes)
            return dict(self._state)

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    # --- control ----------------------------------------------------------

    def start(self) -> dict:
        """Kick off the flow. Returns immediately with state ``pending``."""
        with self._lock:
            if self._state["state"] == "pending":
                return dict(self._state)

            self._cancel.clear()
            self._state = self._idle() | {"state": "pending"}
            thread = threading.Thread(
                target=self._run, name="yandex-device-auth", daemon=True
            )
            self._thread = thread

        thread.start()
        return self.status()

    def cancel(self) -> dict:
        self._cancel.set()
        with self._lock:
            if self._state["state"] == "pending":
                self._state.update(state="cancelled", error=None)
            return dict(self._state)

    def reset(self) -> dict:
        """Forget any previous outcome (used when the token is removed)."""
        self._cancel.set()
        with self._lock:
            self._state = self._idle()
            return dict(self._state)

    # --- worker -----------------------------------------------------------

    def _on_code(self, code) -> None:
        self._update(
            user_code=code.user_code,
            verification_url=code.verification_url,
            expires_in=code.expires_in,
        )

    def _run(self) -> None:
        try:
            client = self._client_factory()
            token = client.device_auth(
                on_code=self._on_code,
                timeout=FLOW_TIMEOUT_S,
                should_cancel=self._cancel.is_set,
                device_name=DEVICE_NAME,
            )
        except yandex_music.exceptions.DeviceAuthError as exc:
            cancelled = self._cancel.is_set() or "cancelled" in str(exc)
            self._finish("cancelled" if cancelled else "error", error=None if cancelled else _describe(exc))
            return
        except Exception as exc:  # network, bad client, anything unexpected
            logger.exception("Yandex device auth failed")
            self._finish("error", error=_describe(exc))
            return

        try:
            self._store_token(token)
        except Exception as exc:
            logger.exception("Could not store the Yandex token")
            self._finish("error", error=f"Токен получен, но не сохранился: {exc}")
            return

        self._finish("success")

    @staticmethod
    def _store_token(token) -> None:
        db.set_setting(TOKEN_KEY, token.access_token)

        if getattr(token, "refresh_token", None):
            db.set_setting(REFRESH_KEY, token.refresh_token)

        expires_in = getattr(token, "expires_in", None)
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            db.set_setting(EXPIRES_KEY, expires_at.isoformat(timespec="seconds"))

        reset_cache()  # drop clients still holding the old credentials
        logger.info("Yandex token stored (expires_in=%s)", expires_in)

    def _finish(self, state: str, error: str | None = None) -> None:
        with self._lock:
            self._state.update(state=state, error=error)
            self._thread = None


yandex_auth = YandexDeviceAuth()
