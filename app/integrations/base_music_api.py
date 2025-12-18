"""Common interface every music service client implements.

All methods return/accept a flat "track" dict:

    {
        "service": "yandex" | "youtube",
        "external_id": str,
        "title": str,
        "artists": str,      # comma separated, ready for display
        "album": str | None,
        "thumbnail": str | None,
        "duration_s": int | None,
    }
"""

from abc import ABC, abstractmethod
from typing import Iterable


class BaseMusicApi(ABC):
    service: str = ""

    @abstractmethod
    def get_liked_tracks(self) -> list[dict]:
        """Return every track in the user's liked library, newest first."""

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search the service for a free-text query and return track candidates."""

    @abstractmethod
    def like_tracks(self, track_ids: Iterable[str]) -> int:
        """Add tracks to the liked library. Returns how many were sent."""

    @abstractmethod
    def unlike_tracks(self, track_ids: Iterable[str]) -> int:
        """Remove tracks from the liked library. Returns how many were sent."""
