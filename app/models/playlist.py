from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .match import Match
from .playlist_track import PlaylistTrack


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    service: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    source_playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE")
    )
    delivery: Mapped[str | None] = mapped_column(String)
    remote_playlist_id: Mapped[str | None] = mapped_column(String)

    source: Mapped["Playlist | None"] = relationship(
        back_populates="targets", remote_side=[id]
    )
    targets: Mapped[list["Playlist"]] = relationship(
        back_populates="source", passive_deletes=True
    )
    entries: Mapped[list["PlaylistTrack"]] = relationship(
        back_populates="playlist",
        order_by="PlaylistTrack.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="playlist", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def kind(self) -> str:
        return "target" if self.source_playlist_id else "imported"
