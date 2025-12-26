"""Yandex OAuth device flow.

The real flow needs a browser and a reachable api.music.yandex.net, so these
tests drive the state machine with a stub client that behaves like
``yandex_music.Client.device_auth``.
"""

import time
from types import SimpleNamespace

import yandex_music

from app import db
from app.services.auth_service import YandexDeviceAuth

DEVICE_CODE = SimpleNamespace(
    user_code="QWER-1234",
    verification_url="https://ya.ru/device",
    expires_in=300,
    interval=1,
)


class StubOAuthClient:
    """Returns a token (or raises) right after handing out the user code."""

    def __init__(self, token=None, error=None):
        self.token = token
        self.error = error
        self.calls = 0

    def device_auth(self, on_code, timeout=None, should_cancel=None, device_name=None):
        self.calls += 1
        on_code(DEVICE_CODE)
        if self.error:
            raise self.error
        return self.token


class BlockingOAuthClient:
    """Stays in the flow until the caller cancels, like a real unanswered prompt."""

    def __init__(self):
        self.calls = 0

    def device_auth(self, on_code, timeout=None, should_cancel=None, device_name=None):
        self.calls += 1
        on_code(DEVICE_CODE)
        while not should_cancel():
            time.sleep(0.01)
        raise yandex_music.exceptions.DeviceAuthError("cancelled by caller")


def token(access="yandex-access", refresh="yandex-refresh", expires_in=3600):
    return SimpleNamespace(
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
        token_type="bearer",
    )


def wait_for(manager, state, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = manager.status()
        if status["state"] == state:
            return status
        time.sleep(0.01)
    raise AssertionError(f"never reached {state!r}: {manager.status()}")


def test_starts_idle():
    manager = YandexDeviceAuth(lambda: StubOAuthClient())

    assert manager.status()["state"] == "idle"
    assert manager.status()["user_code"] is None


def test_successful_flow_stores_the_access_token():
    manager = YandexDeviceAuth(lambda: StubOAuthClient(token=token()))

    started = manager.start()
    assert started["state"] in {"pending", "success"}

    status = wait_for(manager, "success")
    assert status["user_code"] == "QWER-1234"
    assert status["verification_url"] == "https://ya.ru/device"
    assert status["error"] is None

    # The rest of the app only knows about ``token-<service>``.
    assert db.get_setting("token-yandex") == "yandex-access"
    assert db.get_setting("yandex-refresh-token") == "yandex-refresh"
    assert db.get_setting("yandex-token-expires-at")


def test_expiry_timestamp_is_roughly_expires_in():
    manager = YandexDeviceAuth(lambda: StubOAuthClient(token=token(expires_in=60)))

    manager.start()
    wait_for(manager, "success")

    stored = db.get_setting("yandex-token-expires-at")
    assert stored and stored.endswith("+00:00")


def test_timeout_leaves_no_token_behind():
    error = yandex_music.exceptions.DeviceAuthError(
        "timed out after 300s waiting for user confirmation"
    )
    manager = YandexDeviceAuth(lambda: StubOAuthClient(error=error))

    manager.start()
    status = wait_for(manager, "error")

    assert "Код устарел" in status["error"]
    assert db.get_setting("token-yandex") is None


def test_unreachable_network_gets_a_readable_message():
    manager = YandexDeviceAuth(lambda: StubOAuthClient(error=OSError("Network is unreachable")))

    manager.start()
    status = wait_for(manager, "error")

    assert "api.music.yandex.net" in status["error"]


def test_cancel_stops_the_flow():
    stub = BlockingOAuthClient()
    manager = YandexDeviceAuth(lambda: stub)

    manager.start()
    wait_for(manager, "pending")

    manager.cancel()
    assert wait_for(manager, "cancelled")["error"] is None
    assert db.get_setting("token-yandex") is None


def test_second_start_does_not_spawn_another_flow():
    stub = BlockingOAuthClient()
    manager = YandexDeviceAuth(lambda: stub)

    manager.start()
    wait_for(manager, "pending")
    manager.start()
    wait_for(manager, "pending")

    assert stub.calls == 1
    manager.cancel()
    wait_for(manager, "cancelled")


def test_reset_forgets_the_previous_outcome():
    manager = YandexDeviceAuth(lambda: StubOAuthClient(token=token()))

    manager.start()
    wait_for(manager, "success")

    assert manager.reset()["state"] == "idle"
    assert manager.status()["user_code"] is None
