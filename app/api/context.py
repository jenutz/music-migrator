from app.integrations import FULL_NAME, MusicService
from app.services import ImportService

TOKEN_HELP = {
    "yandex": 'Token: <a href="https://yandex-music.readthedocs.io/en/main/token.html" '
              'target="_blank" rel="noopener">instructions</a>',
    "youtube": 'Open <a href="https://music.youtube.com" target="_blank" rel="noopener">music.youtube.com</a>, '
               'F12 → Network, find a request to "/browse" and copy its headers.',
}


def dashboard_context() -> dict:
    return {
        "statuses": {s.value: ImportService.status(s.value) for s in MusicService},
        "fullname": FULL_NAME,
        "services": [s.value for s in MusicService],
        "token_help": TOKEN_HELP,
    }
