import { $, $$, api, toast, formatWhen, formatDuration, escapeHtml, preloadImages } from "./common.js";

const TRACK_URL = {
  yandex: (id) => `https://music.yandex.ru/track/${id}`,
  youtube: (id) => `https://music.youtube.com/watch?v=${id}`,
};

const main = $("#main-content");

function thumbUrl(url, size = "100x100") {
  if (!url) return "";
  return /\/\d+x\d+$/.test(url) ? url.replace(/\/\d+x\d+$/, `/${size}`) : url;
}

function playlistSubtitle(playlist) {
  if (playlist.kind === "imported") {
    return `${playlist.total} tracks`;
  }

  const parts = [`${playlist.applied} of ${playlist.total} delivered`];
  if (playlist.chosen) parts.push(`${playlist.chosen} chosen`);
  if (playlist.total && playlist.applied >= playlist.total) parts.unshift("done");
  return parts.join(" · ");
}

let playlists = [];

function playlistRowHtml(playlist) {
  const target = playlist.kind === "target";

  const origin = target && playlist.source_created_at
    ? `<span class="playlist-origin" title="Source playlist">
         ← ${formatWhen(playlist.source_created_at)}
         <span class="playlist-origin-service">${escapeHtml(playlist.source_service_name || "")}</span>
       </span>`
    : "";

  return `
    <li class="playlist-row${target ? " target" : ""}" data-id="${playlist.id}" data-kind="${playlist.kind}">
      <div class="playlist-meta">
        <span class="playlist-name">${formatWhen(playlist.created_at)}</span>
        <span class="playlist-sub">${escapeHtml(playlistSubtitle(playlist))}</span>
      </div>
      <div class="playlist-actions">
        ${target
          ? `<button data-act="open" title="Continue matching">Continue</button>`
          : `<button data-act="export" title="Create a playlist on another service">Export</button>`}
        <button data-act="view" class="secondary" title="Show the tracks">View</button>
        <button data-act="delete" class="danger" title="Delete this playlist">×</button>
      </div>
      ${origin}
    </li>
  `;
}

function renderPlaylists(data) {
  playlists = data;

  for (const list of $$(".playlist-list")) {
    const service = list.dataset.service;
    const mine = data.filter((playlist) => playlist.service === service);

    list.innerHTML = mine.length
      ? mine.map(playlistRowHtml).join("")
      : `<li class="playlist-empty">no playlists yet</li>`;

    for (const row of $$(".playlist-row", list)) {
      const id = Number(row.dataset.id);
      const playlist = mine.find((item) => item.id === id);

      $('[data-act="open"]', row)?.addEventListener("click", () => {
        location.href = `/migrate/${id}`;
      });
      $('[data-act="export"]', row)?.addEventListener("click", () => renderChooser(playlist));
      $('[data-act="view"]', row)?.addEventListener("click", () => renderPlaylistView(id));
      $('[data-act="delete"]', row)?.addEventListener("click", () => removePlaylist(playlist));
    }
  }
}

async function refreshPlaylists() {
  try {
    const data = await api("/api/playlists");
    renderPlaylists(data.playlists);
  } catch (error) {
    toast(error.message, "err");
  }
}

async function removePlaylist(playlist) {
  const label = formatWhen(playlist.created_at);
  if (!confirm(`Delete the playlist from ${label}?`)) return;

  try {
    await api(`/api/playlist/${playlist.id}`, { method: "DELETE" });
    toast("Playlist deleted", "ok");
    await refreshPlaylists();

    if ($("#workspace")?.dataset.playlist === String(playlist.id)) location.href = "/";
    else if (main.dataset.playlist === String(playlist.id)) location.href = "/";
  } catch (error) {
    toast(error.message, "err");
  }
}

function clearView() {
  delete main.dataset.view;
  delete main.dataset.playlist;
}

function showWelcome() {
  location.href = "/";
}

const DELIVERY_OPTIONS = [
  {
    value: "playlist",
    label: "New playlist",
    hint: "The chosen tracks become a playlist on the selected service.",
  },
  {
    value: "likes",
    label: "Into likes",
    hint: "The chosen tracks are liked in the selected service's library.",
  },
];

function renderChooser(sourcePlaylist) {
  clearView();
  const services = $$(".service-row").map((row) => row.dataset.service);
  let delivery = "playlist";

  main.innerHTML = `
    <div class="main-header">
      <h2>Export playlist</h2>
      <span class="muted">${formatWhen(sourcePlaylist.created_at)} · ${sourcePlaylist.total} tracks</span>
    </div>
    <div class="panel export-panel">
      <h3 class="export-step">Where</h3>
      <div class="delivery-pick">
        ${DELIVERY_OPTIONS.map((option) => `
          <button class="delivery${option.value === delivery ? " active" : ""}"
                  data-delivery="${option.value}">${option.label}</button>
        `).join("")}
      </div>
      <p class="export-hint" id="export-hint"></p>

      <h3 class="export-step">To which service</h3>
      <div class="services-row">
        ${services.map((sid) => {
          const row = $(`.service-row[data-service="${sid}"]`);
          const name = row?.dataset.fullname || sid;
          const ready = !$(".load-btn", row)?.disabled;
          const same = sid === sourcePlaylist.service;
          return `<button class="service-pick" data-dst="${sid}" ${ready ? "" : "disabled"}>
            <img src="/static/${sid}_icon.svg" alt="${sid}">
            <span>${escapeHtml(name)}</span>
            ${same ? "<small>same service</small>" : ""}
            ${ready ? "" : '<small class="muted">no token</small>'}
          </button>`;
        }).join("")}
      </div>
      <p class="export-note">
        The source playlist is not modified — exporting only reads it.
      </p>
    </div>
  `;

  const hint = $("#export-hint", main);
  const paintHint = () => {
    hint.textContent = DELIVERY_OPTIONS.find((option) => option.value === delivery).hint;
    for (const btn of $$(".delivery", main)) {
      btn.classList.toggle("active", btn.dataset.delivery === delivery);
    }
  };
  paintHint();

  for (const btn of $$(".delivery", main)) {
    btn.addEventListener("click", () => {
      delivery = btn.dataset.delivery;
      paintHint();
    });
  }

  for (const btn of $$(".service-pick", main)) {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const result = await api(`/api/export/${sourcePlaylist.id}`, {
          method: "POST",
          body: JSON.stringify({ dst_service: btn.dataset.dst, delivery }),
        });
        await refreshPlaylists();
        toast(result.delivery === "playlist" ? "Playlist created" : "Ready to like the tracks", "ok");
        location.href = `/migrate/${result.playlist_id}`;
      } catch (error) {
        toast(error.message, "err");
        btn.disabled = false;
      }
    });
  }
}

const collator = new Intl.Collator("ru", { sensitivity: "base", numeric: true });

const IMPORTED_COLUMNS = [
  { key: "position", label: "#", numeric: true },
  { key: null, label: "" },
  { key: "title", label: "Title" },
  { key: "artists", label: "Artist" },
  { key: "album", label: "Album" },
  { key: "duration_s", label: "Length", numeric: true },
  { key: "external_id", label: "ID", numeric: true },
];

const TARGET_COLUMNS = [
  { key: "position", label: "#", numeric: true },
  { key: null, label: "" },
  { key: "src_title", label: "Source" },
  { key: "dst_title", label: "Matched" },
  { key: "score", label: "Score", numeric: true },
  { key: "status", label: "Status" },
];

const STATUS_LABEL = {
  chosen: "chosen",
  applied: "delivered",
  skipped: "skipped",
};

function sortRows(rows, key, direction) {
  const sorted = rows.slice();
  if (!key) return sorted.sort((a, b) => b.position - a.position);

  const factor = direction === "desc" ? -1 : 1;

  return sorted.sort((a, b) => {
    const left = a[key];
    const right = b[key];
    const leftEmpty = left === null || left === undefined || left === "";
    const rightEmpty = right === null || right === undefined || right === "";

    if (leftEmpty || rightEmpty) {
      if (leftEmpty && rightEmpty) return 0;
      return leftEmpty ? 1 : -1;
    }
    if (typeof left === "number" && typeof right === "number") {
      return (left - right) * factor;
    }
    return collator.compare(String(left), String(right)) * factor;
  });
}

function rowCover(row) {
  return row.dst_thumbnail || row.thumbnail || row.src_thumbnail;
}

const EAGER_ROWS = 12;

function cellHtml(row, key, service, eager = false) {
  const link = TRACK_URL[service] || (() => "#");

  switch (key) {
    case "position":
      return `<td class="idx">${row.position + 1}</td>`;
    case null: {
      const cover = rowCover(row);
      return `<td class="cover">${cover
        ? `<img class="thumb" src="${thumbUrl(cover)}" alt="" decoding="async" width="48" height="48"
             loading="${eager ? "eager" : "lazy"}" fetchpriority="${eager ? "high" : "auto"}">`
        : ""}</td>`;
    }
    case "duration_s":
      return `<td class="num">${formatDuration(row.duration_s)}</td>`;
    case "external_id":
      return `<td class="mono"><a href="${link(row.external_id)}" target="_blank" rel="noopener">${escapeHtml(row.external_id)}</a></td>`;
    case "src_title":
      return `<td>${escapeHtml(row.src_title || "")}<div class="sub">${escapeHtml(row.src_artists || "")}</div></td>`;
    case "dst_title":
      return row.dst_title
        ? `<td>${escapeHtml(row.dst_title)}<div class="sub">${escapeHtml(row.dst_artists || "")}</div></td>`
        : `<td class="muted-cell">—</td>`;
    case "score":
      return `<td class="num">${row.score ?? "—"}</td>`;
    case "status":
      return `<td>${row.status ? `<span class="status-pill ${row.status}">${STATUS_LABEL[row.status] || row.status}</span>` : '<span class="muted-cell">unreviewed</span>'}</td>`;
    default:
      return `<td>${escapeHtml(row[key] ?? "")}</td>`;
  }
}

function renderTable(container, { columns, rows, service }) {
  const sort = { key: "position", direction: "desc" };
  const PAGE = 80;

  container.innerHTML = `
    <div class="panel table-panel">
      <div class="table-scroll">
        <table class="library">
          <thead>
            <tr>
              ${columns.map((column) => column.key
                ? `<th data-sort="${column.key}" title="Sort">${column.label}<span class="arrow"></span></th>`
                : `<th>${column.label}</th>`).join("")}
            </tr>
          </thead>
          <tbody></tbody>
        </table>
        <div class="table-sentinel"></div>
      </div>
    </div>
  `;

  const scroller = $(".table-scroll", container);
  const tbody = $("tbody", container);
  const sentinel = $(".table-sentinel", container);

  let sorted = [];
  let rendered = 0;
  let observer = null;

  const appendPage = () => {
    const next = sorted.slice(rendered, rendered + PAGE);
    if (!next.length) return;

    tbody.insertAdjacentHTML("beforeend", next.map((row, index) => `
      <tr>${columns.map((column) => cellHtml(row, column.key, service, rendered + index < EAGER_ROWS)).join("")}</tr>
    `).join(""));

    preloadImages(next.slice(0, EAGER_ROWS).map((row) => thumbUrl(rowCover(row))));
    rendered += next.length;

    if (rendered >= sorted.length) stopObserving();
  };

  const stopObserving = () => {
    if (observer) observer.disconnect();
    observer = null;
    sentinel.hidden = true;
  };

  const startObserving = () => {
    sentinel.hidden = false;
    if (!("IntersectionObserver" in window)) {
      while (rendered < sorted.length) appendPage();
      stopObserving();
      return;
    }
    if (observer) observer.disconnect();
    observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) appendPage();
    }, { root: scroller, rootMargin: "300px" });
    observer.observe(sentinel);
  };

  const rebuild = () => {
    sorted = sortRows(rows, sort.key, sort.direction);
    rendered = 0;
    tbody.innerHTML = "";
    scroller.scrollTop = 0;
    appendPage();
    startObserving();
  };

  const renderHeader = () => {
    for (const th of $$("th[data-sort]", container)) {
      const active = th.dataset.sort === sort.key;
      th.classList.toggle("sorted", active);
      th.classList.toggle("desc", active && sort.direction === "desc");
      $(".arrow", th).textContent = active ? (sort.direction === "desc" ? "▼" : "▲") : "";
    }
  };

  $$("th[data-sort]", container).forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sort.key === key) {
        sort.direction = sort.direction === "asc" ? "desc" : "asc";
      } else {
        sort.key = key;
        sort.direction = "asc";
      }
      renderHeader();
      rebuild();
    });
  });

  renderHeader();
  rebuild();
}

async function renderPlaylistView(playlistId) {
  clearView();
  main.dataset.view = "library";
  main.dataset.playlist = String(playlistId);

  main.innerHTML = `
    <div class="main-header"><h2>Loading…</h2></div>
    <div class="panel"><p class="empty">Loading tracks…</p></div>
  `;

  let data;
  try {
    data = await api(`/api/playlist/${playlistId}`);
  } catch (error) {
    main.innerHTML = `<div class="panel empty">${escapeHtml(error.message)}</div>`;
    return;
  }

  const { playlist, tracks } = data;
  const isTarget = playlist.kind === "target";

  const title = `${playlist.service_name} · ${formatWhen(playlist.created_at)}`;
  const subtitle = isTarget
    ? `${playlist.source_name} → ${playlist.applied} of ${playlist.total} delivered`
    : `${tracks.length} tracks`;

  if (!tracks.length) {
    main.innerHTML = `
      <div class="main-header">
        <h2>${escapeHtml(title)}</h2>
        <span class="muted">${escapeHtml(subtitle)}</span>
      </div>
      <div class="panel empty">This playlist is empty.</div>
    `;
    return;
  }

  const body = document.createElement("div");
  body.className = "table-host";

  main.innerHTML = `
    <div class="main-header">
      <h2>${escapeHtml(title)}</h2>
      <span class="muted">${escapeHtml(subtitle)}</span>
    </div>
  `;
  main.appendChild(body);

  renderTable(body, {
    columns: isTarget ? TARGET_COLUMNS : IMPORTED_COLUMNS,
    rows: tracks,
    service: playlist.service,
  });
}

function setConnected(row, connected) {
  const state = $(".service-state", row);
  state.innerHTML = `<span class="dot"></span>${connected ? "connected" : "no token"}`;
  state.classList.toggle("ok", connected);
  $(".load-btn", row).disabled = !connected;
}

function wireDeviceAuth(row, box) {
  const button = $(".device-btn", row);
  if (!button) return;

  const panel = $(".device-panel", row);
  const codeEl = $(".device-code", row);
  const linkEl = $(".device-link", row);
  const statusEl = $(".device-status", row);

  let timer = null;
  const stopPolling = () => {
    if (timer) clearInterval(timer);
    timer = null;
  };

  const showPanel = (status) => {
    panel.hidden = false;
    button.disabled = true;
    statusEl.textContent = status;
  };

  const fail = (message) => {
    stopPolling();
    showPanel(message || "Could not log in");
    button.disabled = false;
  };

  const succeed = () => {
    stopPolling();
    panel.hidden = true;
    button.disabled = false;
    box.classList.remove("open");
    setConnected(row, true);
    toast("Yandex connected", "ok");
  };

  async function poll() {
    let data;
    try {
      data = await api("/api/auth/yandex/status");
    } catch {
      return; // transient hiccup, next tick will retry
    }

    if (data.state === "pending") {
      if (data.user_code) codeEl.textContent = data.user_code;
      if (data.verification_url) linkEl.href = data.verification_url;
      return;
    }

    if (data.state === "success") return succeed();
    if (data.state === "cancelled") {
      stopPolling();
      panel.hidden = true;
      button.disabled = false;
      return;
    }
    if (data.state === "error") return fail(data.error);

    stopPolling();
  }

  button.addEventListener("click", async () => {
    if (timer) return; // already waiting

    codeEl.textContent = "…";
    showPanel("Requesting a code from Yandex…");

    try {
      const data = await api("/api/auth/yandex/start", { method: "POST" });
      if (data.user_code) codeEl.textContent = data.user_code;
      if (data.verification_url) linkEl.href = data.verification_url;
      stopPolling();
      timer = setInterval(poll, 2000);
    } catch (error) {
      fail(error.message);
    }
  });

  $(".device-cancel", row).addEventListener("click", async () => {
    stopPolling();
    panel.hidden = true;
    button.disabled = false;
    try {
      await api("/api/auth/yandex/cancel", { method: "POST" });
    } catch {
    }
  });
}

for (const row of $$(".service-row")) {
  const service = row.dataset.service;
  const box = $(".token-box", row);
  const textarea = $("textarea", box);

  wireDeviceAuth(row, box);

  $(".login-btn", row).addEventListener("click", () => {
    box.classList.toggle("open");
    if (box.classList.contains("open")) textarea.focus();
  });

  $(".cancel-token", row).addEventListener("click", () => {
    box.classList.remove("open");
    textarea.value = "";
  });

  $(".save-token", row).addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const value = textarea.value.trim();
    if (!value) return toast("Paste a token first", "err");

    button.disabled = true;
    try {
      await api(`/api/token/${service}`, { method: "POST", body: JSON.stringify({ value }) });
      textarea.value = "";
      box.classList.remove("open");
      setConnected(row, true);
      toast("Token saved", "ok");
    } catch (error) {
      toast(error.message, "err");
    } finally {
      button.disabled = false;
    }
  });

  $(".clear-btn", row).addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const name = row.dataset.fullname || service;

    const typed = prompt(
      `Remove EVERY like in ${name}?\n\n` +
        "This changes the service itself and cannot be undone. " +
        `Type "${service}" to confirm:`
    );
    if (typed === null) return;
    if (typed.trim().toLowerCase() !== service) return toast("Cancelled", "err");

    button.disabled = true;
    button.textContent = "Clearing…";
    try {
      const result = await api(`/api/service/${service}/clear-likes`, { method: "POST" });
      toast(`Likes removed: ${result.removed}`, "ok");
      await refreshPlaylists();
    } catch (error) {
      toast(error.message, "err");
    } finally {
      button.disabled = false;
      button.textContent = "Clear";
    }
  });

  $(".load-btn", row).addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Importing…";

    try {
      const result = await api(`/api/import/${service}`, { method: "POST" });
      toast(`Tracks imported: ${result.imported}`, "ok");
      await refreshPlaylists();
      renderPlaylistView(result.playlist_id);
    } catch (error) {
      toast(error.message, "err");
    } finally {
      button.disabled = false;
      button.textContent = "Import";
    }
  });
}

refreshPlaylists();

document.addEventListener("playlists:changed", refreshPlaylists);

if (!$("#workspace")) {
  main.dataset.ready = "true";
}
