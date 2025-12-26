import { $, api, toast, formatDuration, escapeHtml } from "./common.js";

const workspace = $("#workspace");
if (workspace) {
  const src = workspace.dataset.src;
  const dst = workspace.dataset.dst;
  const dstName = workspace.dataset.dstName;

  const TRACK_URL = {
    yandex: (id) => `https://music.yandex.ru/track/${id}`,
    youtube: (id) => `https://music.youtube.com/watch?v=${id}`,
  };
  const trackLink = (service, id) => (TRACK_URL[service] ? TRACK_URL[service](id) : "#");

  const state = {
    tracks: [],
    counts: { total: 0, chosen: 0, applied: 0, skipped: 0 },
    activeIndex: 0,
    candidates: new Map(),
  };

  const els = {
    list: $("#track-items"),
    progressBar: $("#progress-bar"),
    progressText: $("#progress-text"),
    sourceCard: $("#source-card"),
    candidates: $("#candidates"),
    empty: $("#empty-state"),
    sourcePane: $("#source-pane"),
    trackIndex: $("#track-index"),
    search: $("#search-form"),
    searchInput: $("#search-input"),
    applyBtn: $("#apply-btn"),
    applyChosen: $("#apply-chosen"),
    applyApplied: $("#apply-applied"),
    applySkipped: $("#apply-skipped"),
    applyTotal: $("#apply-total"),
  };

  const statusOf = (track) => track.status || "todo";
  const currentTrack = () => state.tracks[state.activeIndex];

  // --- rendering ----------------------------------------------------------

  function renderProgress() {
    const { total, chosen, applied, skipped } = state.counts;
    const reviewed = chosen + applied + skipped;
    const percent = total ? Math.round((reviewed / total) * 100) : 0;

    els.progressBar.style.width = `${percent}%`;
    els.progressText.textContent = total
      ? `разобрано ${reviewed} из ${total} · пролайкано ${applied}`
      : "медиатека не загружена";

    const counter = $("#track-count");
    if (counter) counter.textContent = total;

    els.applyChosen.textContent = chosen;
    els.applyApplied.textContent = applied;
    els.applySkipped.textContent = skipped;
    els.applyTotal.textContent = total;

    els.applyBtn.disabled = chosen === 0;
    els.applyBtn.textContent = chosen
      ? `Лайкнуть выбранные (${chosen}) в ${dstName}`
      : "Пока нечего лайкать";
  }

  function renderList() {
    els.list.innerHTML = "";

    state.tracks.forEach((track, index) => {
      const li = document.createElement("li");
      const status = statusOf(track);
      li.className = index === state.activeIndex ? "active" : "";
      li.innerHTML = `
        <span class="idx">${track.position + 1}</span>
        <i class="chip ${status === "todo" ? "" : status}"></i>
        <span class="title">${escapeHtml(track.src_title)}</span>
      `;
      li.addEventListener("click", () => selectTrack(index));
      els.list.appendChild(li);
    });

    const active = els.list.querySelector("li.active");
    if (active) active.scrollIntoView({ block: "nearest" });
  }

  function renderSource() {
    const track = currentTrack();
    if (!track) {
      els.sourceCard.innerHTML = "";
      return;
    }

    const status = statusOf(track);
    els.trackIndex.textContent = `${state.activeIndex + 1} / ${state.tracks.length}`;

    let note = `<p>решение не принято</p>`;
    if (status === "chosen" || status === "applied") {
      const verb = status === "applied" ? "пролайкано как" : "выбрано как";
      note = `<div class="chosen-note">
          <span class="chip ${status}"></span> ${verb}
          <strong>${escapeHtml(track.dst_title || "")}</strong> — ${escapeHtml(track.dst_artists || "")}
        </div>`;
    } else if (status === "skipped") {
      note = `<div class="chosen-note skipped"><span class="chip skipped"></span> пропущено</div>`;
    }

    els.sourceCard.innerHTML = `
      <img src="${track.src_thumbnail || ""}" alt="" onerror="this.style.visibility='hidden'">
      <div class="meta">
        <h4>${escapeHtml(track.src_title)}</h4>
        <p>${escapeHtml(track.src_artists || "")}</p>
        <p>${formatDuration(track.src_duration_s)}</p>
        ${note}
      </div>
      <a class="open-link" href="${trackLink(src, track.src_external_id)}"
         target="_blank" rel="noopener" title="Открыть в исходном сервисе">↗</a>
    `;
  }

  function scoreClass(score) {
    if (score >= 80) return "high";
    if (score >= 55) return "mid";
    return "low";
  }

  function renderCandidates(list) {
    els.candidates.innerHTML = "";

    if (!list.length) {
      els.candidates.innerHTML = `<li style="cursor:default;color:#888">Ничего не найдено. Попробуйте другой запрос.</li>`;
      return;
    }

    list.forEach((candidate, index) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="badge">${index + 1}</span>
        <img src="${candidate.thumbnail || ""}" alt="" onerror="this.style.visibility='hidden'">
        <div class="info">
          <h4>${escapeHtml(candidate.title)}</h4>
          <p>${escapeHtml(candidate.artists || "")}${candidate.album ? " · " + escapeHtml(candidate.album) : ""}</p>
        </div>
        <span style="color:#888">${formatDuration(candidate.duration_s)}</span>
        <span class="score ${scoreClass(candidate.score ?? 0)}">${candidate.score ?? 0}</span>
      `;
      const link = document.createElement("a");
      link.className = "open-link";
      link.href = trackLink(dst, candidate.external_id);
      link.target = "_blank";
      link.rel = "noopener";
      link.title = "Открыть в сервисе назначения";
      link.textContent = "↗";
      link.addEventListener("click", (event) => event.stopPropagation());
      li.appendChild(link);

      li.addEventListener("click", () => choose(candidate));
      els.candidates.appendChild(li);
    });
  }

  // --- data ---------------------------------------------------------------

  async function loadTracks() {
    const data = await api(`/api/tracks?src=${src}&dst=${dst}`);
    state.tracks = data.tracks;
    state.counts = data.counts;

    if (!state.tracks.length) {
      els.empty.hidden = false;
      els.sourcePane.hidden = true;
      els.candidates.innerHTML = "";
      renderProgress();
      return;
    }

    els.empty.hidden = true;
    els.sourcePane.hidden = false;

    const firstUnreviewed = state.tracks.findIndex((track) => statusOf(track) === "todo");
    state.activeIndex = firstUnreviewed === -1 ? 0 : firstUnreviewed;

    renderList();
    renderProgress();
    await selectTrack(state.activeIndex);
  }

  async function selectTrack(index) {
    if (index < 0 || index >= state.tracks.length) return;
    state.activeIndex = index;
    renderList();
    renderSource();
    els.searchInput.value = "";

    const track = currentTrack();
    if (state.candidates.has(track.src_track_id)) {
      renderCandidates(state.candidates.get(track.src_track_id));
    } else {
      await fetchCandidates({ track });
    }
  }

  async function fetchCandidates({ track = currentTrack(), refresh = false, query = null } = {}) {
    if (!track) return;

    els.candidates.innerHTML = `<li style="cursor:default;color:#888">Ищем…</li>`;
    const params = new URLSearchParams({ dst });
    if (refresh) params.set("refresh", "true");
    if (query) params.set("query", query);

    try {
      const data = await api(`/api/candidates/${track.src_track_id}?${params}`);
      state.candidates.set(track.src_track_id, data.candidates);
      if (currentTrack()?.src_track_id === track.src_track_id) {
        renderCandidates(data.candidates);
      }
    } catch (error) {
      els.candidates.innerHTML = `<li style="cursor:default;color:#c62828">${escapeHtml(error.message)}</li>`;
      toast(error.message, "err");
    }
  }

  function advance() {
    const next = state.tracks.findIndex(
      (track, index) => index !== state.activeIndex && statusOf(track) === "todo",
    );
    if (next !== -1) return selectTrack(next);

    const anyTodo = state.tracks.some((track) => statusOf(track) === "todo");
    if (!anyTodo) toast("Все треки разобраны 🎉", "ok");
    else selectTrack(Math.min(state.activeIndex + 1, state.tracks.length - 1));
  }

  async function choose(candidate) {
    const track = currentTrack();
    if (!track) return;

    try {
      await api(`/api/choose/${track.src_track_id}?dst=${dst}`, {
        method: "POST",
        body: JSON.stringify({ external_id: candidate.external_id }),
      });

      if (statusOf(track) !== "chosen" && statusOf(track) !== "applied") state.counts.chosen += 1;
      track.status = "chosen";
      track.dst_title = candidate.title;
      track.dst_artists = candidate.artists;
      track.dst_external_id = candidate.external_id;
      track.score = candidate.score;

      renderProgress();
      await advance();
    } catch (error) {
      toast(error.message, "err");
    }
  }

  async function skip() {
    const track = currentTrack();
    if (!track) return;

    try {
      await api(`/api/skip/${track.src_track_id}?dst=${dst}`, { method: "POST" });

      const was = statusOf(track);
      if (was === "chosen") state.counts.chosen -= 1;
      if (was !== "skipped") state.counts.skipped += 1;
      track.status = "skipped";

      renderProgress();
      await advance();
    } catch (error) {
      toast(error.message, "err");
    }
  }

  async function applyAll() {
    els.applyBtn.disabled = true;
    let applied = 0;

    try {
      for (;;) {
        const result = await api(`/api/apply?src=${src}&dst=${dst}&limit=50`, { method: "POST" });
        applied += result.applied;
        if (applied) toast(`Пролайкано ${applied}…`);
        if (result.done || result.applied === 0) break;
      }

      toast(`${applied} треков пролайкано в ${dstName}`, "ok");
      await loadTracks();
    } catch (error) {
      toast(error.message, "err");
      els.applyBtn.disabled = false;
    }
  }

  // --- events -------------------------------------------------------------

  els.applyBtn.addEventListener("click", applyAll);
  $("#prev-track").addEventListener("click", () => selectTrack(state.activeIndex - 1));
  $("#next-track").addEventListener("click", () => selectTrack(state.activeIndex + 1));

  els.search.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = els.searchInput.value.trim();
    fetchCandidates({ refresh: true, query: query || null });
  });

  document.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea, select")) return;

    if (event.key === "s") { event.preventDefault(); skip(); return; }
    if (event.key === "n") { event.preventDefault(); selectTrack(state.activeIndex + 1); return; }
    if (event.key === "p") { event.preventDefault(); selectTrack(state.activeIndex - 1); return; }
    if (event.key === "ArrowDown") { event.preventDefault(); selectTrack(state.activeIndex + 1); return; }
    if (event.key === "ArrowUp") { event.preventDefault(); selectTrack(state.activeIndex - 1); return; }

    const digit = Number(event.key);
    if (!Number.isNaN(digit) && digit >= 1 && digit <= 9) {
      const list = state.candidates.get(currentTrack()?.src_track_id) || [];
      const candidate = list[digit - 1];
      if (candidate) { event.preventDefault(); choose(candidate); }
    }
  });

  loadTracks().catch((error) => toast(error.message, "err"));
}
