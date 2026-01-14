const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

let toastTimer;

export function toast(message, kind = "") {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast ${kind}`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3600);
}

export async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = { detail: text }; }

  if (!response.ok) {
    throw new Error(payload?.detail || `Ошибка запроса (${response.status})`);
  }
  return payload;
}

// Timestamps are stored in UTC; show them in the browser's own timezone so a
// playlist row and the workspace header never disagree.
export function formatWhen(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso || "";
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()}`
    + ` ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatDuration(seconds) {
  if (!seconds) return "—";
  const total = Number(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

const preloaded = new Set();

// Ask the browser to fetch covers before the <img> tags are parsed/inserted.
// The request is deduplicated with the later <img src>, so this only moves it
// earlier - which is the difference between a cover appearing instantly and
// appearing after the row is already on screen.
export function preloadImages(urls) {
  for (const url of urls) {
    if (!url || preloaded.has(url)) continue;
    preloaded.add(url);

    const link = document.createElement("link");
    link.rel = "preload";
    link.as = "image";
    link.fetchPriority = "high";
    link.href = url;
    document.head.appendChild(link);
  }
}

export { $, $$ };
