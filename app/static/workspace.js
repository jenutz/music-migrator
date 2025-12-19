import { $, $$, api, toast } from "./common.js";

const workspace = $("#workspace");
const src = workspace.dataset.src;
const dst = workspace.dataset.dst;

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
  trackIndex: $("#track-index"),
  search: $("#search-form"),
  searchInput: $("#search-input"),
  applyBtn: $("#apply-btn"),
  applyChosen: $("#apply-chosen"),
  applyApplied: $("#apply-applied"),
  applySkipped: $("#apply-skipped"),
  applyTotal: $("#apply-total"),
};

const STATUS_LABEL = { chosen: "chosen", applied: "applied", skipped: "skipped" };

function currentTrack() {
  return state.tracks[state.activeIndex];
}

function statusOf(track) {
  return track.status || "todo";
}

// --- rendering ------------------------------------------------------------

function renderProgress() {
  const { total, chosen, applied, skipped } = state.counts;
  const done = chosen + applied + skipped;
  const percent = total ? Math.round((done / total) * 100) : 0;

  els.progressBar.style.width = `${percent}%`;
  els.progressText.textContent = total
    ? `${done} / ${total} reviewed · ${applied} applied`
    : "Nothing imported";

  els.applyChosen.textContent = chosen;
  els.applyApplied.textContent = applied;
  els.applySkipped.textContent = skipped;
  els.applyTotal.textContent = total;
  els.applyBtn.disabled = chosen === 0;
  els.applyBtn.textContent = chosen
    ? `Like ${chosen} chosen track${chosen === 1 ? "" : "s"} on ${workspace.dataset.dstName}`
    : `Nothing to like yet`;
}

function renderList() {
  els.list.innerHTML = "";

  state.tracks.forEach((track, index) => {
    const li = document.createElement("li");
    li.className = index === state.activeIndex ? "active" : "";
    li.dataset.index = String(index);
    li.innerHTML = `
      <span class="idx">${track.position + 1}</span>
      <i class="chip ${statusOf(track) === "todo" ? "" : statusOf(track)}"></i>
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

  const match = status === "chosen" || status === "applied"
    ? `<p class="small"><span class="chip ${status}"></span> ${STATUS_LABEL[status]} as
         <strong>${escapeHtml(track.dst_title || "")}</strong> — ${escapeHtml(track.dst_artists || "")}</p>`
    : status === "skipped"
      ? `<p class="small muted"><span class="chip skipped"></span> skipped</p>`
      : `<p class="small muted">no choice yet</p>`;

  els.sourceCard.innerHTML = `
    <img src="${track.src_thumbnail || ""}" alt="" onerror="this.style.visibility='hidden'">
    <div class="meta">
      <h4>${escapeHtml(track.src_title)}</h4>
      <p>${escapeHtml(track.src_artists || "")}</p>
      <p class="small muted">${formatDuration(track.src_duration_s)} · ${escapeHtml(src)}</p>
      ${match}
    </div>
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
    els.candidates.innerHTML = `<li class="muted small">No results. Try a different search query.</li>`;
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
      <span class="small muted">${formatDuration(candidate.duration_s)}</span>
      <span class="score ${scoreClass(candidate.score ?? 0)}">${candidate.score ?? 0}</span>
      <button class="btn secondary pick">Use</button>
    `;
    li.addEventListener("click", () => choose(candidate));
    els.candidates.appendChild(li);
  });
}

// --- data -----------------------------------------------------------------

async function loadTracks() {
  const data = await api(`/api/tracks?src=${src}&dst=${dst}`);
  state.tracks = data.tracks;
  state.counts = data.counts;

  if (!state.tracks.length) {
    els.empty.hidden = false;
    $("#source-pane").hidden = true;
    els.candidates.innerHTML = "";
    renderProgress();
    return;
  }

  els.empty.hidden = true;
  $("#source-pane").hidden = false;

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

  const track = currentTrack();
  els.searchInput.value = "";

  if (state.candidates.has(track.src_track_id)) {
    renderCandidates(state.candidates.get(track.src_track_id));
  } else {
    await fetchCandidates({ track });
  }
}

async function fetchCandidates({ track = currentTrack(), refresh = false, query = null } = {}) {
  if (!track) return;

  els.candidates.innerHTML = `<li class="muted small">Searching…</li>`;
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
    els.candidates.innerHTML = `<li class="muted small">${escapeHtml(error.message)}</li>`;
    toast(error.message, "err");
  }
}

function advance() {
  const next = state.tracks.findIndex(
    (track, index) => index !== state.activeIndex && statusOf(track) === "todo",
  );
  if (next !== -1) return selectTrack(next);

  const anyTodo = state.tracks.some((track) => statusOf(track) === "todo");
  if (!anyTodo) toast("All tracks reviewed 🎉", "ok");
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

    track.status = "chosen";
    track.dst_title = candidate.title;
    track.dst_artists = candidate.artists;
    track.dst_external_id = candidate.external_id;
    track.score = candidate.score;

    state.counts.chosen += 1;
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
    if (statusOf(track) !== "skipped") state.counts.skipped += 1;
    if (statusOf(track) === "chosen") state.counts.chosen -= 1;
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
      toast(`Liked ${applied} tracks…`);

      if (result.done || result.applied === 0) break;
    }

    toast(`${applied} tracks liked on ${workspace.dataset.dstName}`, "ok");
    await loadTracks();
  } catch (error) {
    toast(error.message, "err");
    els.applyBtn.disabled = false;
  }
}

// --- events ---------------------------------------------------------------

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

// --- utils ----------------------------------------------------------------

function formatDuration(seconds) {
  if (!seconds) return "";
  const total = Number(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

loadTracks().catch((error) => toast(error.message, "err"));
