/* CharlaViva shared front-end helpers: i18n, WebSocket with reconnect, formatting. */

const I18N = {
  es: {
    pick: "Elegí una sesión",
    pick_sub: "Subtítulos simultáneos en vivo: transcripción en el idioma original y traducción en tiempo real. Elegí el escenario y el idioma que querés leer.",
    live: "EN VIVO",
    offline: "sin conexión",
    reconnecting: "reconectando…",
    waiting: "Esperando audio en vivo…",
    bilingual: "Original + traducción",
    original: "Original",
    latency: "latencia",
    back: "← Sesiones",
    engine: "motor",
    admin_title: "Producción · CharlaViva",
    new_session: "Nueva sesión",
    name: "Nombre",
    source_type: "Fuente",
    source_path: "Archivo o URL",
    speed: "Velocidad",
    loop: "Repetir en loop",
    src_lang: "Idioma de entrada",
    outputs: "Idiomas de salida",
    glossary: "Glosario (términos técnicos, nombres)",
    glossary_ph: "Nerdearla, Kubernetes, Grafana…",
    engine_pick: "Motor",
    create: "Crear y transmitir",
    load_demo: "Cargar demo (2+ sesiones)",
    actions: "Acciones",
    state: "Estado",
    session: "Sesión",
    finals: "finales",
    export: "Exportar",
    auto: "auto",
    no_sessions: "Sin sesiones todavía. Cargá la demo o creá una arriba.",
    confirm_delete: "¿Borrar esta sesión y su historial?",
    mic_help: "mic: creá la sesión y abrí la vista de audiencia para dar permiso de micrófono",
  },
  en: {
    pick: "Pick a session",
    pick_sub: "Live simultaneous captions: transcription in the original language plus real-time translation. Choose the stage and the language you want to read.",
    live: "LIVE",
    offline: "disconnected",
    reconnecting: "reconnecting…",
    waiting: "Waiting for live audio…",
    bilingual: "Original + translation",
    original: "Original",
    latency: "latency",
    back: "← Sessions",
    engine: "engine",
    admin_title: "Production · CharlaViva",
    new_session: "New session",
    name: "Name",
    source_type: "Source",
    source_path: "File or URL",
    speed: "Speed",
    loop: "Loop",
    src_lang: "Input language",
    outputs: "Output languages",
    glossary: "Glossary (technical terms, names)",
    glossary_ph: "Nerdearla, Kubernetes, Grafana…",
    engine_pick: "Engine",
    create: "Create & go live",
    load_demo: "Load demo (2+ sessions)",
    actions: "Actions",
    state: "State",
    session: "Session",
    finals: "finals",
    export: "Export",
    auto: "auto",
    no_sessions: "No sessions yet. Load the demo or create one above.",
    confirm_delete: "Delete this session and its history?",
    mic_help: "mic: create the session and open the audience view to grant microphone access",
  },
};

let UI_LANG = localStorage.getItem("cv_lang") || "es";
function t(key) {
  return (I18N[UI_LANG] && I18N[UI_LANG][key]) || I18N.es[key] || key;
}
function setLang(lang) {
  UI_LANG = lang;
  localStorage.setItem("cv_lang", lang);
  applyI18n();
}
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPh);
  });
  document.querySelectorAll("[data-i18n-toggle]").forEach((el) => {
    el.textContent = UI_LANG === "es" ? "EN" : "ES";
  });
}

const LANG_NAMES = { es: "Español", en: "English", pt: "Português", fr: "Français" };
function langName(code) {
  return LANG_NAMES[code] || (code || "").toUpperCase();
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function fmtMs(ms) {
  if (!ms && ms !== 0) return "—";
  return ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : Math.round(ms) + "ms";
}

/* connectWS(url, {onMessage, onOpen, onClose}) → {close()} with auto-reconnect */
function connectWS(url, handlers = {}) {
  let ws = null;
  let closedByUs = false;
  let retry = 0;
  let timer = null;

  function open() {
    ws = new WebSocket(url);
    ws.onopen = () => {
      retry = 0;
      handlers.onOpen && handlers.onOpen();
    };
    ws.onmessage = (ev) => {
      if (ev.data === "pong") return;
      try {
        handlers.onMessage && handlers.onMessage(JSON.parse(ev.data));
      } catch (e) { /* ignore malformed */ }
    };
    ws.onclose = () => {
      handlers.onClose && handlers.onClose();
      if (!closedByUs) {
        timer = setTimeout(open, Math.min(8000, 500 * 2 ** retry++));
      }
    };
    ws.onerror = () => ws.close();
  }
  open();
  return {
    close() { closedByUs = true; clearTimeout(timer); ws && ws.close(); },
    send(obj) { ws && ws.readyState === 1 && ws.send(JSON.stringify(obj)); },
  };
}

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/* Browser microphone → PCM16/16k mono binary frames over WebSocket. */
async function startMic(sessionId, onState) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const source = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const ws = new WebSocket(`/ws/audio/${sessionId}`);
  ws.binaryType = "arraybuffer";
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

  function downsample(f32, fromRate) {
    const ratio = fromRate / 16000;
    const outLen = Math.floor(f32.length / ratio);
    const out = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const idx = Math.floor(i * ratio);
      const s = Math.max(-1, Math.min(1, f32[idx]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return new Uint8Array(out.buffer);
  }

  proc.onaudioprocess = (e) => {
    if (ws.readyState === 1) {
      ws.send(downsample(e.inputBuffer.getChannelData(0), ctx.sampleRate));
    }
  };
  source.connect(proc);
  // keep the processor alive without monitoring the mic through the speakers
  const mute = ctx.createGain();
  mute.gain.value = 0;
  proc.connect(mute);
  mute.connect(ctx.destination);
  onState && onState("live");
  return {
    stop() {
      ws.send('{"type":"end"}');
      ws.close();
      proc.disconnect();
      stream.getTracks().forEach((tr) => tr.stop());
      ctx.close();
      onState && onState("stopped");
    },
  };
}
