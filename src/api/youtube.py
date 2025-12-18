import ytmusicapi
from .base_music_api import BaseMusicApi
import re


class YoutubeClient(BaseMusicApi):
    def __init__(self, token: str | None = None):
        if token is None:
            self.ytmusic = ytmusicapi.YTMusic()
        else:
            auth = ytmusicapi.setup(headers_raw=token)
            self.ytmusic = ytmusicapi.YTMusic(auth)

    def get_track(self, track_id: str):
        target = self.ytmusic.get_song(videoId=track_id)
        target = YoutubeClient._normalize_get_song(target)
        return target

    @staticmethod
    def _normalize_get_song(track):
        all_thumbnails = track["videoDetails"]["thumbnail"]["thumbnails"]
        thumbnail = YoutubeClient._extract_biggest_thumbnail(all_thumbnails)
        return {
            "id": track["videoDetails"]["videoId"],
            "title": track["videoDetails"]["title"],
            "artists": track["videoDetails"]["author"],
            "album": (track.get("album") or {}).get("name"),
            "thumbnail": thumbnail,
            "duratio_s": track["videoDetails"]["lengthSeconds"],
        }

    def search(self, target: str):
        matches = self.ytmusic.search(target)
        all_normalized = []
        for e in matches:
            if e["resultType"] != "song":
                continue
            norm = YoutubeClient._normalize_track(e)
            all_normalized.append(norm)
        return all_normalized

    @staticmethod
    def _normalize_track(track):
        thumbnail = YoutubeClient._extract_biggest_thumbnail(track["thumbnails"])
        album = track.get("album", None)
        if album is not None:
            album = album["name"]

        return {
            "id": track["videoId"],
            "title": track["title"],
            "artists": ", ".join(str(e["name"]) for e in track["artists"]),
            "album": (track.get("album") or {}).get("name"),
            "thumbnail": thumbnail,
            "duration_s": track.get("duration_seconds"),
        }

    @staticmethod
    def _extract_biggest_thumbnail(thumbnails):
        defalt_thumbnail = thumbnails[-1] if thumbnails else None
        return next((e for e in thumbnails if e["width"] >= 200), defalt_thumbnail)["url"]

    def get_liked_tracks(self):
        songs = self.ytmusic.get_playlist("LM", None)["tracks"]

        norm_songs = []

        for song in reversed(songs):
            norm = YoutubeClient._normalize_track(song)
            norm_songs.append(norm)

        return norm_songs

    def remove_tags(res):
        res = re.sub(r"\(Remastered \d{4}\)", "", res)
        res = re.sub(r"\(\d{4} Remaster\s*\)", "", res)
        pattern = r"[\(\[](?:digital|\d\d\d\d|master|official|music|video|audio|lyrics|lyric|hd|hq|remastered|visualizer)(?:\s+(?:digital|\d\d\d\d|master|official|music|video|audio|lyrics|lyric|hd|hq|remastered|visualizer))*[\)\]]"
        res = re.sub(pattern, "", res, flags=re.IGNORECASE)
        pattern = r"(?i)\b(digital|\d\d\d\d|master|official|music|video|audio|lyrics|lyric|hd|hq|remastered|visualizer)\b"
        res = re.sub(pattern, "", res)
        res = re.sub(r"\s+", " ", res)
        return res


