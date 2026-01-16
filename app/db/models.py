"""``Playlist`` points at itself: a target remembers which import it was
exported from, and its tracks come from ``Match`` rows, not from copies in
``playlist_tracks``.
"""

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


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


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    service: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    source_playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE")
    )
    # targets only: 'likes' (like the tracks) or 'playlist' (build a playlist)
    delivery: Mapped[str | None] = mapped_column(String)
    # remote playlist id once the destination playlist actually exists
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


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (Index("idx_playlist_tracks", "playlist_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)

    playlist: Mapped[Playlist] = relationship(back_populates="entries")
    track: Mapped[Track] = relationship(lazy="joined")

    def as_dict(self) -> dict:
        return {**self.track.as_dict(), "position": self.position}


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("dst_playlist_id", "src_track_id"),
        Index("idx_matches_status", "dst_playlist_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dst_playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    src_track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    dst_external_id: Mapped[str | None] = mapped_column(String)
    dst_title: Mapped[str | None] = mapped_column(String)
    dst_artists: Mapped[str | None] = mapped_column(String)
    dst_album: Mapped[str | None] = mapped_column(String)
    dst_thumbnail: Mapped[str | None] = mapped_column(String)
    dst_duration_s: Mapped[int | None]
    score: Mapped[int | None]
    status: Mapped[str] = mapped_column(String, nullable=False, default="chosen")
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    playlist: Mapped[Playlist] = relationship(back_populates="matches")


class SearchCache(Base):
    __tablename__ = "search_cache"

    src_track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    dst_service: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
