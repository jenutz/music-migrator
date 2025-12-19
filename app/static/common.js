const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

let toastTimer;

export function toast(message, kind = "") {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast ${kind}`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
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
    throw new Error(payload?.detail || `Request failed (${response.status})`);
  }
  return payload;
}

export function withBusy(button, fn) {
  return async (...args) => {
    if (!button) return fn(...args);
    button.disabled = true;
    button.classList.add("loading");
    try {
      return await fn(...args);
    } finally {
      button.classList.remove("loading");
      button.disabled = false;
    }
  };
}

export { $, $$ };
