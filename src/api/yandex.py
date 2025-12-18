import yandex_music
from .base_music_api import BaseMusicApi

class YandexClient(BaseMusicApi):
    def __init__(self, token: str | None = None):
        if token is None:
            self.ydmusic = yandex_music.Client().init()
        else:
            self.ydmusic = yandex_music.Client(token).init()

    def get_track(self, track_id: str):
        target = self.ydmusic.tracks(track_id)[0]
        target = YandexClient._normalize(target)
        return target

    @staticmethod
    def _normalize(track: yandex_music.Track):
        return {
            "id" : track.id,
            "title": track.title,
            "artists": ", ".join(e.name for e in track.artists),
            "album": track.albums[0].title,
            "thumbnail": track.albums[0].get_cover_url("200x200"),
            "duration_s": track.duration_ms // 1000,
        }

    def search(self, target: str):
        matches = self.ydmusic.search(target, type_="track").tracks.results
        matches = [YandexClient._normalize(e) for e in matches]
        return matches

    def get_liked_tracks(self):
        songs = self.ydmusic.users_likes_tracks().fetch_tracks()
        norm_songs = []

        for song in reversed(songs):
            norm = YandexClient._normalize(song)
            norm_songs.append(norm)
        return norm_songs


if __name__ == "__main__":
    API_KEY = "y0__xD1jp6aAhje-AYgnpi7iBYwlcac7gfP04bRFNv9N4P3Vd9j77EugaKXxQ"
    import src.settings as settings
    import src.api.factory
    print(settings.get("token-yandex"))
    
    
    y = YandexClient(API_KEY)
    res = y.ydmusic.users_likes_tracks().fetch_tracks()
    print(res)
    # print(res[0])
    # input("Press Enter to continue...")
    # print(res[-1])
    # input("Press Enter to continue...")
    # print(len(res))
