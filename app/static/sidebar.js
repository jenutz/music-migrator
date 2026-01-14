import { $, $$, api, toast, formatWhen, formatDuration, escapeHtml, preloadImages } from "./common.js";

const TRACK_URL = {
  yandex: (id) => `https://music.yandex.ru/track/${id}`,
  youtube: (id) => `https://music.youtube.com/watch?v=${id}`,
};

const main = $("#main-content");

// --- helpers --------------------------------------------------------------

// Covers are stored at 200x200; ask the service for something near the size we
// actually paint so a long library does not fetch full-size images.
function thumbUrl(url, size = "100x100") {
  if (!url) return "";
  return /\/\d+x\d+$/.test(url) ? url.replace(/\/\d+x\d+$/, `/${size}`) : url;
}

function playlistSubtitle(playlist) {
  if (playlist.kind === "imported") {
    return `${playlist.total} треков`;
  }

  const parts = [`пролайкано ${playlist.applied} из ${playlist.total}`];
  if (playlist.chosen) parts.push(`выбрано ${playlist.chosen}`);
  if (playlist.total && playlist.applied >= playlist.total) parts.unshift("готово");
  return parts.join(" · ");
}

// --- playlist list --------------------------------------------------------

let playlists = [];

function playlistRowHtml(playlist) {
  const target = playlist.kind === "target";

  // A target playlist is only meaningful next to the snapshot it came from,
  // so spell that out under the row instead of a bare service name.
  const origin = target && playlist.source_created_at
    ? `<span class="playlist-origin" title="Исходный плейлист">
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
          ? `<button data-act="open" title="Продолжить сопоставление">Продолжить</button>`
          : `<button data-act="export" title="Создать плейлист в другом сервисе">Экспорт</button>`}
        <button data-act="view" class="secondary" title="Показать треки">Просмотр</button>
        <button data-act="delete" class="danger" title="Удалить плейлист">×</button>
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
      : `<li class="playlist-empty">плейлистов пока нет</li>`;

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
  if (!confirm(`Удалить плейлист ${label}?`)) return;

  try {
    await api(`/api/playlist/${playlist.id}`, { method: "DELETE" });
    toast("Плейлист удалён", "ok");
    await refreshPlaylists();

    // the open workspace belonged to it, go home
    if ($("#workspace")?.dataset.playlist === String(playlist.id)) location.href = "/";
    else if (main.dataset.playlist === String(playlist.id)) location.href = "/";
  } catch (error) {
    toast(error.message, "err");
  }
}

// --- views ----------------------------------------------------------------

function clearView() {
  delete main.dataset.view;
  delete main.dataset.playlist;
}

function showWelcome() {
  location.href = "/";
}

function renderChooser(sourcePlaylist) {
  clearView();
  const others = $$(".service-row")
    .map((row) => row.dataset.service)
    .filter((service) => service !== sourcePlaylist.service);

  main.innerHTML = `
    <div class="main-header">
      <h2>Экспорт плейлиста</h2>
      <span class="muted">${formatWhen(sourcePlaylist.created_at)} · ${sourcePlaylist.total} треков</span>
    </div>
    <div class="panel">
      <p style="margin-top:0;color:#555">
        Будет создан новый плейлист в выбранном сервисе. Выборы сохраняются в нём,
        исходный плейлист остаётся нетронутым.
      </p>
      <div class="services-row">
        ${others.map((sid) => {
          const row = $(`.service-row[data-service="${sid}"]`);
          const name = row?.dataset.fullname || sid;
          const ready = !$(".load-btn", row)?.disabled;
          return `<button class="service-pick" data-dst="${sid}" ${ready ? "" : "disabled"}>
            <img src="/static/${sid}_icon.svg" alt="${sid}">
            <span>${escapeHtml(name)}</span>
            ${ready ? "" : '<small style="color:#999">нет токена</small>'}
          </button>`;
        }).join("")}
      </div>
    </div>
  `;

  $$(".service-pick", main).forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const result = await api(`/api/export/${sourcePlaylist.id}`, {
          method: "POST",
          body: JSON.stringify({ dst_service: btn.dataset.dst }),
        });
        await refreshPlaylists();
        location.href = `/migrate/${result.playlist_id}`;
      } catch (error) {
        toast(error.message, "err");
        btn.disabled = false;
      }
    });
  });
}

// --- library table --------------------------------------------------------

const collator = new Intl.Collator("ru", { sensitivity: "base", numeric: true });

const IMPORTED_COLUMNS = [
  { key: "position", label: "#", numeric: true },
  { key: null, label: "" },
  { key: "title", label: "Название" },
  { key: "artists", label: "Исполнитель" },
  { key: "album", label: "Альбом" },
  { key: "duration_s", label: "Время", numeric: true },
  { key: "external_id", label: "ID", numeric: true },
];

const TARGET_COLUMNS = [
  { key: "position", label: "#", numeric: true },
  { key: null, label: "" },
  { key: "src_title", label: "Было" },
  { key: "dst_title", label: "Стало" },
  { key: "score", label: "Совпадение", numeric: true },
  { key: "status", label: "Статус" },
];

const STATUS_LABEL = {
  chosen: "выбрано",
  applied: "пролайкано",
  skipped: "пропущено",
};

// position 0 is the oldest liked track, so "latest to oldest" is position
// descending - that is also the default view.
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

// Match rows carry src_thumbnail/dst_thumbnail, imported rows just thumbnail.
function rowCover(row) {
  return row.dst_thumbnail || row.thumbnail || row.src_thumbnail;
}

// The first screenful is what the eye lands on, so it loads eagerly; the rest
// stays lazy so opening a 1900-track playlist does not fire 1900 requests.
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
      return `<td>${row.status ? `<span class="status-pill ${row.status}">${STATUS_LABEL[row.status] || row.status}</span>` : '<span class="muted-cell">не разобрано</span>'}</td>`;
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
                ? `<th data-sort="${column.key}" title="Сортировать">${column.label}<span class="arrow"></span></th>`
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
    <div class="main-header"><h2>Загрузка…</h2></div>
    <div class="panel"><p class="empty">Загружаем треки…</p></div>
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
    ? `${playlist.source_name} → пролайкано ${playlist.applied} из ${playlist.total}`
    : `${tracks.length} треков`;

  if (!tracks.length) {
    main.innerHTML = `
      <div class="main-header">
        <h2>${escapeHtml(title)}</h2>
        <span class="muted">${escapeHtml(subtitle)}</span>
      </div>
      <div class="panel empty">Плейлист пуст.</div>
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

// --- sidebar wiring -------------------------------------------------------

function setConnected(row, connected) {
  const state = $(".service-state", row);
  state.innerHTML = `<span class="dot"></span>${connected ? "подключён" : "нет токена"}`;
  state.classList.toggle("ok", connected);
  $(".load-btn", row).disabled = !connected;
}

// --- yandex device flow ---------------------------------------------------

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
    showPanel(message || "Не удалось войти");
    button.disabled = false;
  };

  const succeed = () => {
    stopPolling();
    panel.hidden = true;
    button.disabled = false;
    box.classList.remove("open");
    setConnected(row, true);
    toast("Яндекс подключён", "ok");
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
    showPanel("Запрашиваем код у Яндекса…");

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
      /* nothing useful to do here */
    }
  });
}

// --- service rows ---------------------------------------------------------

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
    if (!value) return toast("Вставьте токен", "err");

    button.disabled = true;
    try {
      await api(`/api/token/${service}`, { method: "POST", body: JSON.stringify({ value }) });
      textarea.value = "";
      box.classList.remove("open");
      setConnected(row, true);
      toast("Токен сохранён", "ok");
    } catch (error) {
      toast(error.message, "err");
    } finally {
      button.disabled = false;
    }
  });

  $(".load-btn", row).addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Загружаем…";

    try {
      const result = await api(`/api/import/${service}`, { method: "POST" });
      toast(`Загружено треков: ${result.imported}`, "ok");
      await refreshPlaylists();
      renderPlaylistView(result.playlist_id);
    } catch (error) {
      toast(error.message, "err");
    } finally {
      button.disabled = false;
      button.textContent = "Загрузить";
    }
  });
}

refreshPlaylists();

// the workspace refreshes the counters after it likes a batch
document.addEventListener("playlists:changed", refreshPlaylists);

// the migrate page ships its own workspace script; don't clobber it
if (!$("#workspace")) {
  main.dataset.ready = "true";
}
