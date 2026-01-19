from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("service", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    artists: Mapped[str | None] = mapped_column(String)
    album: Mapped[str | None] = mapped_column(String)
    thumbnail: Mapped[str | None] = mapped_column(String)
    duration_s: Mapped[int | None]

    def as_dict(self) -> dict:
        return {
            "service": self.service,
            "external_id": self.external_id,
            "title": self.title,
            "artists": self.artists,
            "album": self.album,
            "thumbnail": self.thumbnail,
            "duration_s": self.duration_s,
        }
