from enum import Enum

from .base_music_api import BaseMusicApi
from .yandex import YandexClient
from .youtube import YoutubeClient


class MusicService(str, Enum):
    yandex = "yandex"
    youtube = "youtube"


FULL_NAME = {
    "yandex": "Yandex Music",
    "youtube": "YouTube Music",
}

# Where a track lives, used for the "open in service" links.
TRACK_URL = {
    "yandex": "https://music.yandex.ru/track/{id}",
    "youtube": "https://music.youtube.com/watch?v={id}",
}

_CLIENTS = {
    MusicService.yandex: YandexClient,
    MusicService.youtube: YoutubeClient,
}

# Clients hold open HTTP sessions, so they are built once and reused.
_cache: dict[tuple[str, str | None], BaseMusicApi] = {}


def choose_api(service: MusicService | str, token: str | None = None) -> BaseMusicApi:
    service = MusicService(service)
    key = (service.value, token)
    if key not in _cache:
        _cache[key] = _CLIENTS[service](token)
    return _cache[key]


def reset_cache() -> None:
    _cache.clear()


def other_services(service: MusicService | str) -> list[str]:
    return [s.value for s in MusicService if s.value != MusicService(service).value]
