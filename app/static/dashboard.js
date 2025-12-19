import { $, $$, api, toast } from "./common.js";

const cards = $$(".service-card");

function statusLine(card, message, kind = "") {
  const line = $(".status-line", card);
  line.textContent = message;
  line.className = `status-line small ${kind}`;
}

for (const card of cards) {
  const service = card.dataset.service;
  const tokenInput = $(".token-input", card);
  const saveBtn = $(".save-token", card);
  const clearBtn = $(".clear-token", card);
  const importBtn = $(".import-btn", card);

  saveBtn.addEventListener("click", async () => {
    const value = tokenInput.value.trim();
    if (!value) return toast("Paste a token first", "err");

    saveBtn.disabled = true;
    try {
      await api(`/api/token/${service}`, { method: "POST", body: JSON.stringify({ value }) });
      tokenInput.value = "";
      importBtn.disabled = false;
      clearBtn.disabled = false;
      statusLine(card, "Token saved", "ok");
      toast("Token saved", "ok");
    } catch (error) {
      statusLine(card, error.message, "err");
      toast(error.message, "err");
    } finally {
      saveBtn.disabled = false;
    }
  });

  clearBtn.addEventListener("click", async () => {
    try {
      await api(`/api/token/${service}`, { method: "DELETE" });
      importBtn.disabled = true;
      clearBtn.disabled = true;
      statusLine(card, "Token cleared", "ok");
    } catch (error) {
      toast(error.message, "err");
    }
  });

  importBtn.addEventListener("click", async () => {
    importBtn.disabled = true;
    statusLine(card, "Fetching library… this can take a minute");
    try {
      const result = await api(`/api/import/${service}`, { method: "POST" });
      statusLine(card, `Imported ${result.imported} tracks`, "ok");
      toast(`${result.imported} tracks imported`, "ok");
      const counter = $("p.muted.small", card);
      counter.innerHTML = `<span class="dot ok"></span>Connected · ${result.imported} tracks imported`;
      importBtn.textContent = "Re-import library";
    } catch (error) {
      statusLine(card, error.message, "err");
      toast(error.message, "err");
    } finally {
      importBtn.disabled = false;
    }
  });
}

// --- migrate form ---------------------------------------------------------

const srcSelect = $("#src-select");
const dstSelect = $("#dst-select");

function syncSelects() {
  const same = srcSelect.value === dstSelect.value;
  $("#migrate-form button[type=submit]").disabled = same;
}

srcSelect.addEventListener("change", syncSelects);
dstSelect.addEventListener("change", syncSelects);
syncSelects();

$("#swap").addEventListener("click", () => {
  [srcSelect.value, dstSelect.value] = [dstSelect.value, srcSelect.value];
  syncSelects();
});

$("#migrate-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (srcSelect.value === dstSelect.value) return toast("Pick two different services", "err");
  window.location.href = `/migrate/${srcSelect.value}/${dstSelect.value}`;
});
