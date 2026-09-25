/* CharlaViva — production monitor: create/stop sessions, live metrics, exports. */

document.getElementById("lang-toggle").addEventListener("click", () => {
  setLang(UI_LANG === "es" ? "en" : "es");
});

const body = document.getElementById("sessions-body");

async function refresh() {
  try {
    const [sessions, health] = await Promise.all([
      fetchJSON("/api/sessions"),
      fetchJSON("/api/health"),
    ]);
    document.getElementById("health-badge").innerHTML =
      `<span class="dot live"></span> ⚙️ ${escapeHtml(health.engine_default)}` +
      (health.gemini_configured ? " · ✨gemini" : "") +
      (health.whisper_available ? " · 🧠whisper" : "");
    document.getElementById("session-count").textContent = sessions.length;
    render(sessions);
  } catch (e) {
    document.getElementById("health-badge").innerHTML =
      `<span class="dot error"></span> ${t("offline")}`;
  }
}

function render(sessions) {
  document.getElementById("admin-empty").hidden = sessions.length > 0;
  body.innerHTML = "";
  for (const s of sessions) {
    const st = s.stats || {};
    const tr = document.createElement("tr");
    const lastErr = st.errors && st.errors.length ? st.errors[st.errors.length - 1].message : "";
    const stateCls = s.state === "running" ? "live" : s.state === "error" ? "error" : "stopped";
    const idShort = s.id.length > 18 ? s.id.slice(0, 18) + "…" : s.id;
    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(s.name)}</strong><br />
        <span class="mini mono" title="${escapeHtml(s.id)}">${escapeHtml(idShort)}</span>
        <span class="chip">${escapeHtml(s.src_lang)}</span>
        ${(s.outputs || []).map((o) => `<span class="chip">${escapeHtml(o)}</span>`).join("")}
        ${lastErr ? `<div class="mini err">${escapeHtml(lastErr)}</div>` : ""}
      </td>
      <td><span class="dot ${stateCls}"></span> ${escapeHtml(s.state)}
        ${s.source && s.source.desc ? `<div class="mini">${escapeHtml(String(s.source.desc).slice(0, 42))}</div>` : ""}</td>
      <td class="mini">${escapeHtml(st.engine || s.engine || "-")}</td>
      <td class="mono">${fmtMs(st.latency_p50_ms)} / ${fmtMs(st.latency_last_ms)}</td>
      <td class="mono">${st.finals ?? 0}<div class="mini">⏱ ${escapeHtml(fmtMs(st.latency_p90_ms))} p90</div></td>
      <td class="row-actions">
        ${s.state === "running"
          ? `<button data-act="stop">⏸</button>`
          : `<button data-act="start">▶</button>`}
        <button data-act="del" class="danger">🗑</button>
        <a href="/api/sessions/${s.id}/export?format=srt&lang=es">SRT</a>
        <a href="/api/sessions/${s.id}/export?format=vtt&lang=es">VTT</a>
        <a href="/api/sessions/${s.id}/export?format=txt&lang=es">TXT</a>
        <a href="/overlay?session=${s.id}&lang=es" target="_blank">🎥 overlay</a>
      </td>`;
    tr.querySelectorAll("[data-act]").forEach((btn) => {
      btn.onclick = () => action(btn.dataset.act, s.id);
    });
    body.appendChild(tr);
  }
}

async function action(act, id) {
  if (act === "del" && !confirm(t("confirm_delete"))) return;
  const routes = {
    start: `/api/sessions/${id}/start`,
    stop: `/api/sessions/${id}/stop`,
    del: `/api/sessions/${id}`,
  };
  await fetch(routes[act], { method: act === "del" ? "DELETE" : "POST" }).catch(() => {});
  refresh();
}

document.getElementById("demo-btn").addEventListener("click", async () => {
  await fetch("/api/demo?n=2", { method: "POST" }).catch(() => {});
  refresh();
});

document.getElementById("create-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const outputs = ["es", "en", "pt"].filter((o) => f.get(`out_${o}`));
  const type = f.get("type");
  const spec = {
    name: f.get("name"),
    source: {
      type,
      path: type === "stream" ? "" : f.get("path"),
      url: type === "stream" ? f.get("path") : "",
      speed: parseFloat(f.get("speed") || "1"),
      loop: f.get("loop") === "on",
    },
    src_lang: f.get("src_lang"),
    outputs: outputs.length ? outputs : ["es"],
    glossary: String(f.get("glossary") || "").split(/[,\n]/).map((s) => s.trim()).filter(Boolean),
    engine: f.get("engine") || null,
  };
  await fetchJSON("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
  ev.target.reset();
  refresh();
});

applyI18n();
refresh();
setInterval(refresh, 2500);
