/* CharlaViva — OBS browser-source overlay: transparent rolling captions.
   Params:
     session=ID        (required) session to follow
     lang=es|en|pt     language to show (default: es)
     bilingual=1       show original + translation
     max=3             finalized lines kept on screen
     size=40           base font size (px)
     pos=bottom|top    anchor (default bottom)
*/
const params = new URLSearchParams(location.search);
const sessionId = params.get("session");
const lang = params.get("lang") || "es";
const bilingual = params.get("bilingual") === "1";
const maxLines = Math.max(1, parseInt(params.get("max") || "3", 10));
const size = Math.max(12, parseInt(params.get("size") || "40", 10));

if ((params.get("pos") || "bottom") === "top") document.body.classList.add("top");
document.getElementById("stack").style.fontSize = size + "px";

const stackEl = document.getElementById("stack");
let finals = [];
let partial = null;

function textFor(ev) {
  return (ev.texts && (ev.texts[lang] || Object.values(ev.texts)[0])) || "";
}
function srcFor(ev) {
  return (ev.texts && ev.texts[ev.src_lang]) || "";
}

function render() {
  const items = finals.slice(-maxLines);
  let html = "";
  for (const ev of items) {
    const main = textFor(ev);
    const sub = bilingual ? srcFor(ev) : "";
    html += `<div class="ov-session">
      ${sub && sub !== main ? `<div class="ov-src" style="font-size:0.65em">${escapeHtml(sub)}</div>` : ""}
      <div class="ov-tr" style="color:#fff">${escapeHtml(main)}</div>
    </div>`;
  }
  if (partial) {
    const main = textFor(partial);
    if (main) {
      html += `<div class="ov-session partial">
        <div class="ov-tr" style="color:#fff">${escapeHtml(main)}</div>
      </div>`;
    }
  }
  stackEl.innerHTML = html;
}

if (!sessionId) {
  stackEl.innerHTML = `<div class="ov-session" style="color:#fff">overlay: falta ?session=ID</div>`;
} else {
  connectWS(`/ws/captions/${sessionId}`, {
    onMessage(msg) {
      if (msg.type === "history") {
        finals = msg.events.filter((e) => e.kind === "final");
        render();
      } else if (msg.type === "caption") {
        const ev = msg.event;
        if (ev.kind === "final") { finals.push(ev); partial = null; }
        else if (ev.kind === "partial") partial = ev;
        render();
      }
    },
  });
}
