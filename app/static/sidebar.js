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
  state.innerHTML = `<span class="dot"></span>${connected ? "подключён" : "нет токена"}`;
  state.classList.toggle("ok", connected);

  row.dataset.imported = String(imported || 0);

  const placeholder = $(".placeholder-text", row);
  placeholder.textContent = imported
    ? `Загружено треков: ${imported}`
    : "Медиатека ещё не загружена";

  $(".load-btn", row).disabled = !connected;
  $(".view-btn", row).disabled = !imported;
  $(".export-btn", row).disabled = !imported;
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
    setState(row, true, Number(row.dataset.imported || 0));
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

for (const row of $$(".service-row")) {
  const service = row.dataset.service;
  const fullname = row.dataset.fullname;
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
      setState(row, true, Number(row.dataset.imported || 0));
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
