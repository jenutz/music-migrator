import { $, $$, api, toast, formatDuration, escapeHtml } from "./common.js";

const TRACK_URL = {
  yandex: (id) => `https://music.yandex.ru/track/${id}`,
  youtube: (id) => `https://music.youtube.com/watch?v=${id}`,
};

const main = $("#main-content");

// --- shared views ---------------------------------------------------------

function showWelcome() {
  location.href = "/";
}

function renderChooser(sourceService, sourceName) {
  const others = $$(".service-row")
    .map((row) => row.dataset.service)
    .filter((svc) => svc !== sourceService);

  main.innerHTML = `
    <div class="main-header">
      <h2>Экспорт из ${escapeHtml(sourceName)}</h2>
      <span class="muted">выберите сервис назначения</span>
    </div>
    <div class="panel">
      <div class="services-row">
        ${others.map((sid) => {
          const row = $(`.service-row[data-service="${sid}"]`);
          const name = row?.dataset.fullname || sid;
          return `<button class="service-pick" data-dst="${sid}">
            <img src="/static/${sid}_icon.svg" alt="${sid}">
            <span>${escapeHtml(name)}</span>
          </button>`;
        }).join("")}
      </div>
    </div>
  `;

  $$(".service-pick", main).forEach((btn) => {
    btn.addEventListener("click", () => {
      location.href = `/migrate/${sourceService}/${btn.dataset.dst}`;
    });
  });
}

async function renderLibrary(service, serviceName) {
  main.innerHTML = `
    <div class="main-header">
      <h2>${escapeHtml(serviceName)}</h2>
      <span class="muted" id="library-count">загрузка…</span>
    </div>
    <div class="panel"><p class="empty">Загружаем треки…</p></div>
  `;

  let data;
  try {
    data = await api(`/api/library/${service}`);
  } catch (error) {
    main.innerHTML = `<div class="panel empty">${escapeHtml(error.message)}</div>`;
    return;
  }

  if (!data.tracks.length) {
    main.innerHTML = `
      <div class="main-header"><h2>${escapeHtml(serviceName)}</h2></div>
      <div class="panel empty">Медиатека пуста — нажмите «Загрузить».</div>
    `;
    return;
  }

  const link = TRACK_URL[service] || (() => "#");

  main.innerHTML = `
    <div class="main-header">
      <h2>${escapeHtml(serviceName)}</h2>
      <span class="muted" id="library-count">${data.tracks.length} треков</span>
    </div>
    <div class="panel" style="overflow:auto">
      <table class="library">
        <thead>
          <tr>
            <th>#</th><th></th><th>Название</th><th>Исполнитель</th><th>Альбом</th><th>Время</th><th>ID</th>
          </tr>
        </thead>
        <tbody>
          ${data.tracks.map((track, index) => `
            <tr>
              <td>${index + 1}</td>
              <td>${track.thumbnail ? `<img class="thumb" src="${track.thumbnail}" alt="">` : ""}</td>
              <td>${escapeHtml(track.title)}</td>
              <td>${escapeHtml(track.artists || "")}</td>
              <td>${escapeHtml(track.album || "")}</td>
              <td>${formatDuration(track.duration_s)}</td>
              <td class="mono"><a href="${link(track.external_id)}" target="_blank" rel="noopener">${escapeHtml(track.external_id)}</a></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// --- sidebar wiring -------------------------------------------------------

function setState(row, connected, imported) {
  const state = $(".service-state", row);
  state.textContent = connected ? "подключён" : "нет токена";
  state.classList.toggle("ok", connected);

  const placeholder = $(".placeholder-text", row);
  placeholder.textContent = imported
    ? `Загружено треков: ${imported}`
    : "Медиатека ещё не загружена";

  $(".load-btn", row).disabled = !connected;
  $(".view-btn", row).disabled = !imported;
  $(".export-btn", row).disabled = !imported;
}

for (const row of $$(".service-row")) {
  const service = row.dataset.service;
  const fullname = row.dataset.fullname;
  const box = $(".token-box", row);
  const textarea = $("textarea", box);

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
      setState(row, true, Number($(".placeholder-text", row).dataset.imported || 0));
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
    const placeholder = $(".placeholder-text", row);
    placeholder.textContent = "Загружаем медиатеку…";

    try {
      const result = await api(`/api/import/${service}`, { method: "POST" });
      setState(row, true, result.imported);
      toast(`Загружено треков: ${result.imported}`, "ok");
    } catch (error) {
      placeholder.textContent = error.message;
      toast(error.message, "err");
    } finally {
      button.disabled = false;
    }
  });

  $(".view-btn", row).addEventListener("click", () => renderLibrary(service, fullname));
  $(".export-btn", row).addEventListener("click", () => renderChooser(service, fullname));
}

// the migrate page ships its own workspace script; don't clobber it
if ($("#workspace")) {
  // sidebar handlers above are already attached; nothing else to do
} else {
  main.dataset.ready = "true";
}
