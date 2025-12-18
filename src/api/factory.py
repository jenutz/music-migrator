from enum import Enum
from .yandex import YandexClient
from .youtube import YoutubeClient


class MusicService(str, Enum):
    youtube = "youtube"
    yandex = "yandex"


FULL_NAME = {"youtube": "Youtube Music", "yandex": "Yandex Music"}


def choose_api(service: MusicService, token: str | None = None):
    match service:
        case MusicService.youtube:
            return YoutubeClient(token)
        case MusicService.yandex:
            return YandexClient(token)
