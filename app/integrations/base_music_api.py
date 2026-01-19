from abc import ABC, abstractmethod
from typing import Iterable


class BaseMusicApi(ABC):
    service: str = ""

    @abstractmethod
    def get_liked_tracks(self) -> list[dict]: ...

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[dict]: ...

    @abstractmethod
    def like_tracks(self, track_ids: Iterable[str]) -> int: ...

    @abstractmethod
    def unlike_tracks(self, track_ids: Iterable[str]) -> int: ...

    @abstractmethod
    def create_playlist(self, name: str, track_ids: Iterable[str] = ()) -> str: ...

    @abstractmethod
    def add_playlist_tracks(self, playlist_id: str, track_ids: Iterable[str]) -> int: ...
