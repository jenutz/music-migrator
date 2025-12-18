from abc import ABC, abstractmethod

class BaseMusicApi(ABC):
    @abstractmethod
    def __init__(self, token: str | None = None):
        pass

    @abstractmethod
    def get_track(self, track_id: str):
        pass


    @abstractmethod
    def search(self, target: str):
        pass

    @abstractmethod
    def get_liked_tracks(self) -> list[dict]:
        pass