from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


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

    playlist: Mapped["Playlist"] = relationship(back_populates="matches")
