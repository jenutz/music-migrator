"""Candidate search + similarity scoring, scoped to one target playlist."""

import difflib
import functools
import logging
import re
import sqlite3

from app import db
from app.integrations.factory import choose_api
from app.integrations.youtube import strip_tags

logger = logging.getLogger(__name__)

try:  # rapidfuzz is much faster and gives better partial ratios
    from rapidfuzz import fuzz as _fuzz  # type: ignore
except ImportError:  # pragma: no cover - fallback keeps the app usable
    _fuzz = None


_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")


@functools.lru_cache(maxsize=8192)
def _norm(text: str | None) -> str:
    text = strip_tags(text or "")
    text = _BRACKETS.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip().lower()


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if _fuzz is not None:
        return float(_fuzz.token_set_ratio(a, b))
    return difflib.SequenceMatcher(None, a, b).ratio() * 100.0


def score_track(source: dict, candidate: dict) -> int:
    """0-100 confidence that `candidate` is the same recording as `source`."""
    title_score = _ratio(_norm(source["title"]), _norm(candidate.get("title")))
    artist_score = _ratio(_norm(source["artists"]), _norm(candidate.get("artists")))

    score = title_score * 0.6 + artist_score * 0.4

    # A wildly different runtime is usually a live/remix/covers mix-up.
    src_d, dst_d = source.get("duration_s"), candidate.get("duration_s")
    if src_d and dst_d:
        delta = abs(int(src_d) - int(dst_d))
        if delta > 30:
            score -= min(25, (delta - 30) * 0.5)
        elif delta <= 5:
            score += 5

    if candidate.get("result_type") == "video":
        score -= 8  # music videos sit below proper song uploads

    return max(0, min(100, round(score)))


class MatchService:
    """Works on one target playlist: search, choose, skip."""

    LOCAL_GOOD_ENOUGH = 88
    LOCAL_MIN_SCORE = 45
    LOCAL_SPREAD = 15
    LOCAL_LIMIT = 10

    def __init__(self, dst_playlist_id: int):
        playlist = db.get_playlist(dst_playlist_id)
        if not playlist:
            raise ValueError(f"Unknown playlist {dst_playlist_id}")
        if not playlist["source_playlist_id"]:
            raise ValueError(f"Playlist {dst_playlist_id} is not a migration target")

        self.playlist = playlist
        self.playlist_id = int(playlist["id"])
        self.dst_service = playlist["service"]
        self.src_playlist_id = int(playlist["source_playlist_id"])

    # --- candidates ------------------------------------------------------

    def _local_candidates(self, source: sqlite3.Row) -> list[dict]:
        """Ids from here are likeable without a round trip."""
        scorer_input = dict(source)
        found = []

        for row in db.tracks_for_service(self.dst_service):
            candidate = dict(row)
            candidate["score"] = score_track(scorer_input, candidate)
            if candidate["score"] >= self.LOCAL_MIN_SCORE:
                candidate["origin"] = "db"
                found.append(candidate)

        found.sort(key=lambda item: item["score"], reverse=True)
        if not found:
            return []

        cutoff = max(self.LOCAL_MIN_SCORE, found[0]["score"] - self.LOCAL_SPREAD)
        return [candidate for candidate in found if candidate["score"] >= cutoff][: self.LOCAL_LIMIT]

    @classmethod
    def _merge(cls, local: list[dict], remote: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}

        for candidate in remote:
            merged[str(candidate.get("external_id"))] = candidate
        for candidate in local:
            key = str(candidate.get("external_id"))
            existing = merged.get(key)
            if existing is None or existing.get("score", 0) < candidate["score"]:
                merged[key] = candidate

        results = list(merged.values())
        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return results[: cls.LOCAL_LIMIT]

    def candidates(self, src_track_id: int, refresh: bool = False, query: str | None = None) -> list[dict]:
        source = db.get_track(src_track_id)
        if not source:
            raise ValueError(f"Unknown track {src_track_id}")

        if not refresh and not query:
            cached = db.get_cached_search(src_track_id, self.dst_service)
            if cached is not None:
                return cached

        local = [] if query else self._local_candidates(source)

        if local and local[0]["score"] >= self.LOCAL_GOOD_ENOUGH and not refresh:
            # not cached: it is a view of the library as it is right now
            logger.info("Answered %r from the local library", source["title"])
            return local

        token = db.get_setting(f"token-{self.dst_service}")
        client = choose_api(self.dst_service, token)
        search_query = query or f"{source['title']} {source['artists']}"

        logger.info("Searching %s for %r", self.dst_service, search_query)
        remote = client.search(search_query, limit=10)

        for result in remote:
            result["score"] = score_track(dict(source), result)
            result["origin"] = "search"

        results = self._merge(local, remote)
        db.set_cached_search(src_track_id, self.dst_service, results)
        return results

    # --- choices ---------------------------------------------------------

    def choose(self, src_track_id: int, candidate: dict) -> dict:
        source = db.get_track(src_track_id)
        if not source:
            raise ValueError(f"Unknown track {src_track_id}")
        if not candidate.get("external_id"):
            raise ValueError("Candidate has no external id")

        db.save_match(
            dst_playlist_id=self.playlist_id,
            src_track_id=src_track_id,
            track=candidate,
            score=candidate.get("score"),
        )
        return {"src_track_id": src_track_id, "status": "chosen"}

    def choose_by_id(self, src_track_id: int, external_id: str) -> dict:
        """Pick a candidate the UI showed, by its external id."""
        for candidate in db.get_cached_search(src_track_id, self.dst_service) or []:
            if candidate.get("external_id") == external_id:
                return self.choose(src_track_id, candidate)

        # Local answers are deliberately not cached, so score the library again
        # instead of telling the user their own click was invalid.
        source = db.get_track(src_track_id)
        if not source:
            raise ValueError(f"Unknown track {src_track_id}")

        for candidate in self._local_candidates(source):
            if candidate.get("external_id") == external_id:
                return self.choose(src_track_id, candidate)

        raise ValueError(f"Candidate {external_id} not found for track {src_track_id}")

    def skip(self, src_track_id: int) -> dict:
        db.skip_match(self.playlist_id, src_track_id)
        return {"src_track_id": src_track_id, "status": "skipped"}

    def build_target(self, src_track_id: int) -> dict:
        """Attach the stored match to a source track, for rendering."""
        source = db.get_track(src_track_id)
        match = db.get_match(self.playlist_id, src_track_id)
        return {"source": dict(source) if source else None, "match": dict(match) if match else None}
