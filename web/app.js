/* CharlaViva — audience view: lobby of live stages + big rolling captions. */

const lobbyEl = document.getElementById("lobby");
const stageEl = document.getElementById("stage");
const gridEl = document.getElementById("session-grid");
const captionBox = document.getElementById("caption-box");

let sessions = [];
let current = null;         // session dict
let currentWs = null;
let finals = [];            // finalized caption events
let partial = null;         // in-flight partial event
let currentLang = "src";    // 'src' or language code
let bilingual = localStorage.getItem("cv_bilingual") === "1";

const bilingualToggle = document.getElementById("bilingual-toggle");
bilingualToggle.checked = bilingual;
bilingualToggle.addEventListener("change", () => {
  bilingual = bilingualToggle.checked;
  localStorage.setItem("cv_bilingual", bilingual ? "1" : "0");
  renderCaptions();
});

document.getElementById("lang-toggle").addEventListener("click", () => {
  setLang(UI_LANG === "es" ? "en" : "es");
  renderLobby();
  renderTabs();
});

/* ---------------- lobby ---------------- */
async function loadSessions() {
  try {
    sessions = await fetchJSON("/api/sessions");
    const health = await fetchJSON("/api/health").catch(() => null);
    if (health) {
      document.getElementById("engine-pills").innerHTML = [
        `<span class="badge">⚙️ ${escapeHtml(health.engine_default)}</span>`,
        health.gemini_configured ? `<span class="badge ok">✨ Gemini</span>` : "",
        health.whisper_available ? `<span class="badge ok">🧠 Whisper local</span>` : "",
      ].join("");
    }
    renderLobby();
  } catch (e) {
    setConn("offline");
  }
}

function renderLobby() {
  gridEl.innerHTML = "";
  document.getElementById("lobby-empty").hidden = sessions.length > 0;
  for (const s of sessions) {
    const card = document.createElement("div");
    card.className = "card";
    const langs = [s.src_lang !== "auto" ? s.src_lang : "?", ...s.outputs]
      .map((l) => `<span class="chip">${escapeHtml(l)}</span>`).join("");
    const last = s.last_texts
      ? Object.values(s.last_texts)[0] || ""
      : "";
    card.innerHTML = `
      <h3><span class="dot ${s.state === "running" ? "live" : s.state === "error" ? "error" : "stopped"}"></span>
        ${escapeHtml(s.name)}</h3>
      <div class="meta">${langs}<span class="badge">${escapeHtml(s.stats.engine || s.engine)}</span></div>
      <div class="last">${escapeHtml(last || t("waiting"))}</div>`;
    card.onclick = () => openStage(s);
    gridEl.appendChild(card);
  }
}

function setConn(state) {
  const pill = document.getElementById("conn-badge");
  const text = document.getElementById("conn-text");
  const dot = pill.querySelector(".dot");
  dot.className = "dot " + (state === "live" ? "live" : state === "offline" ? "error" : "");
  text.textContent = state === "live" ? t("live") : state === "offline" ? t("offline") : t("reconnecting");
}

/* ---------------- stage ---------------- */
function sessionLangs(s) {
  const src = s.src_lang && s.src_lang !== "auto" ? s.src_lang : (s.last_src || "src");
  return { src, all: [src, ...s.outputs.filter((o) => o !== src)] };
}

function openStage(s) {
  current = s;
  finals = [];
  partial = null;
  currentLang = localStorage.getItem(`cv_lang_${s.id}`) || "src";
  lobbyEl.hidden = true;
  stageEl.hidden = false;
  document.getElementById("stage-title").textContent = s.name;
  ["srt", "vtt", "txt"].forEach((fmt) => {
    document.getElementById(`ex-${fmt}`).href = `/api/sessions/${s.id}/export?format=${fmt}`;
    document.getElementById(`ex-${fmt}`).download = "";
  });
  const micBtn = document.getElementById("mic-btn");
  micBtn.hidden = !(s.source && s.source.type === "mic");
  renderTabs();
  renderCaptions();
  if (currentWs) currentWs.close();
  currentWs = connectWS(`/ws/captions/${s.id}`, {
    onOpen: () => setConn("live"),
    onClose: () => setConn("reconnect"),
    onMessage: onWsMessage,
  });
}

/* --- microphone sessions --- */
let micHandle = null;
const micBtn = document.getElementById("mic-btn");
micBtn.addEventListener("click", async () => {
  if (!current) return;
  if (micHandle) {
    micHandle.stop();
    micHandle = null;
    micBtn.textContent = "🎙️ Usar micrófono";
    return;
  }
  try {
    micHandle = await startMic(current.id, () => {});
    micBtn.textContent = "⏹ Cortar micrófono";
  } catch (e) {
    alert("No se pudo acceder al micrófono: " + e.message);
  }
});

document.getElementById("back-btn").addEventListener("click", () => {
  if (currentWs) currentWs.close();
  currentWs = null;
  current = null;
  stageEl.hidden = true;
  lobbyEl.hidden = false;
  loadSessions();
});

function onWsMessage(msg) {
  if (msg.type === "hello") {
    current = msg.session;
    renderTabs();
  } else if (msg.type === "history") {
    finals = [];
    for (const ev of msg.events) {
      if (ev.kind === "final") finals.push(ev);
    }
    renderCaptions();
  } else if (msg.type === "caption") {
    const ev = msg.event;
    if (ev.kind === "final") {
      finals.push(ev);
      if (finals.length > 200) finals.shift();
      partial = null;
    } else if (ev.kind === "partial") {
      partial = ev;
    }
    if (ev.latency_ms !== undefined) {
      document.getElementById("latency-pill").textContent = `${t("latency")} ${fmtMs(ev.latency_ms)}`;
    }
    renderCaptions();
  }
}

function renderTabs() {
  if (!current) return;
  const { src, all } = sessionLangs(current);
  const tabs = document.getElementById("lang-tabs");
  tabs.innerHTML = "";
  for (const code of all) {
    const b = document.createElement("button");
    b.textContent = code === src ? `${t("original")} · ${langName(src)}` : langName(code);
    b.className = (currentLang === code || (currentLang === "src" && code === src)) ? "active" : "";
    b.onclick = () => {
      currentLang = code;
      localStorage.setItem(`cv_lang_${current.id}`, code);
      renderTabs();
      renderCaptions();
    };
    tabs.appendChild(b);
  }
}

function textFor(ev, code) {
  if (code === "src") {
    return ev.texts[ev.src_lang] || Object.values(ev.texts)[0] || "";
  }
  return ev.texts[code] || "";
}

function renderCaptions() {
  if (!current) return;
  const { src } = sessionLangs(current);
  const code = currentLang === "src" ? src : currentLang;
  const items = finals.slice(-2);
  let html = "";
  if (!items.length && !partial) {
    captionBox.innerHTML = `<div class="empty">${t("waiting")}</div>`;
    return;
  }
  items.forEach((ev, i) => {
    const cls = i === items.length - 1 ? "" : "old";
    html += capHtml(ev, code, src, cls);
  });
  if (partial) html += capHtml(partial, code, src, "partial");
  captionBox.innerHTML = html;
  captionBox.scrollTop = captionBox.scrollHeight;
}

function capHtml(ev, code, src, extra) {
  const main = textFor(ev, code) || textFor(ev, src);
  const sub = bilingual ? textFor(ev, src) : "";
  const subIsMain = sub === main;
  return `<div class="cap ${extra}">
    <div class="line-main">${escapeHtml(main)}</div>
    ${bilingual && sub && !subIsMain ? `<div class="line-sub">${escapeHtml(sub)}</div>` : ""}
  </div>`;
}

/* keep lobby cards fresh */
setInterval(() => { if (stageEl.hidden) loadSessions(); }, 4000);
applyI18n();
loadSessions();
