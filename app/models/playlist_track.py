from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .track import Track


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (Index("idx_playlist_tracks", "playlist_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)

    playlist: Mapped["Playlist"] = relationship(back_populates="entries")
    track: Mapped[Track] = relationship(lazy="joined")

    def as_dict(self) -> dict:
        return {**self.track.as_dict(), "position": self.position}
