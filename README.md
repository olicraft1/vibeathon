<p align="center"><strong>🧉 CharlaViva</strong></p>
<p align="center">
  <em>Subtítulos simultáneos open source para conferencias · Open source live captions &amp; simultaneous translation</em><br/>
  <a href="README.md">Español</a> · <a href="#-english">English</a> ·
  <a href="docs/ARCHITECTURE.md">Arquitectura</a> ·
  <a href="docs/DEPLOY.md">Deploy &amp; escala</a> ·
  <a href="docs/OBS.md">OBS/vMix</a> ·
  <a href="docs/DEMO_SCRIPT.md">Demo video</a>
</p>

---

En **Nerdearla** queremos que el evento sea accesible para todas las personas. La transcripción simultánea comercial no escala: este año hay **más de 30 sesiones en inglés, muchas en simultáneo**. CharlaViva es la respuesta open source: toma el audio en vivo de un escenario y produce **subtítulos en tiempo real** — transcripción en el idioma original **y traducción al español (o al inglés)** — para **tantas sesiones en paralelo** como tengas.

## ✨ Qué hace

- 🎙️ **Audio en vivo desde 3 fuentes**: micrófono del navegador, archivo de audio (mp3/wav/m4a/ogg…) o stream (HLS/m3u8, HTTP, RTMP — lo que salga de OBS/vMix).
- 📝 **Transcripción en tiempo real** del idioma original (inglés, español, portugués…).
- 🌍 **Traducción en tiempo real** EN→ES, ES→EN (y más idiomas: `pt`, `fr`).
- 👥 **Vista para la audiencia**: cada persona elige la sesión y el idioma, en cualquier celular o notebook.
- 🎥 **Overlay para OBS/vMix**: quemá los subtítulos en el stream con un Browser Source.
- 🗂️ **Export** al terminar cada charla: **SRT / VTT / texto**.
- 🎛️ **Panel de producción**: estado de cada sesión, latencia, errores — para el equipo técnico del evento.
- 📚 **Glosario** de términos técnicos y nombres propios (¡Nerdearla no es "Nerd-larla"!).
- 🔀 **N sesiones en simultáneo** (5, 10, 30…) sobre una misma máquina; escala a más nodos sin cambios de código.

## 🚀 Arrancá en 60 segundos

```bash
git clone https://github.com/olicraft1/vibeathon.git && cd vibeathon
pip install -r requirements.txt
python -m charlaviva demo          # ← 2 escenarios de muestra, ya transmitiendo
```

Abrí **http://localhost:8000** (audiencia), **/admin** (producción) o **/overlay** (OBS). Listo: hay subtítulos EN→ES y ES→EN corriendo en dos sesiones en paralelo sobre los audios de prueba incluidos en [`samples/`](samples/README.md).

Después probá con **audio real de una charla de Nerdearla**:

```bash
./scripts/fetch_talk.sh "https://www.youtube.com/watch?v=ID_DE_CHARLA"
# y creá la sesión desde /admin apuntando al archivo descargado
```

### Motores (elegí calidad y dependencias)

| Motor | Transcripción | Traducción | Requisitos | Latencia típica |
|---|---|---|---|---|
| **gemini** ⭐ recomendado | Gemini Live (`gemini-3.8-live`, `gemini-3.5-transcribe-live`) | ✅ EN↔ES↔PT en el mismo stream | `GEMINI_API_KEY` (capa gratuita) | ~0.5–1.5 s |
| **whisper** 100 % local | faster-whisper (offline, cualquier idioma) | ✅ → inglés nativo; ES/PT vía Gemini (opcional) | `pip install faster-whisper` (descarga el modelo) | ~1–3 s (CPU) |
| **canned** (fallback) | pistas pre-armadas de los samples | ✅ | nada — cero modelos | ~0 s |

La selección es automática (`CHARLAVIVA_ENGINE=auto`): gemini si hay API key, si no whisper, si no canned. Configurá todo en [`.env`](.env.example).

```bash
cp .env.example .env          # y agregá GEMINI_API_KEY=… para máxima calidad
python -m charlaviva serve    # sin samples: levantás solo el servidor
python -m charlaviva doctor   # chequeá que todo esté instalado
```

## 📸 Para la audiencia

Cada persona abre la página, elige el escenario y el idioma (p. ej. *Original · English* o *Español*):

- subtítulos **parciales** en gris mientras la persona habla, **finales** al cerrar la idea
- modo **bilingüe** (original + traducción) para seguir ambos a la vez
- badge de **latencia** en vivo
- export de la charla en **SRT / VTT / TXT** cuando termina

Funciona en celular sin instalar nada. La UI es bilingüe ES/EN.

## 🏗️ Cómo funciona

```
 mic / archivo / stream ──▶ PCM16 @16 kHz ──▶ VAD ──▶ Motor (gemini | whisper | canned)
                                                        │  eventos de caption
                                                        ▼
                                        SessionManager (N sesiones en asyncio)
                                                        │  WebSocket
                          ┌─────────────────────────────┼───────────────────────┐
                          ▼                             ▼                       ▼
                   👥 Audiencia (web)            🎥 Overlay OBS          🎛️ Producción (/admin)
                   idioma + bilingüe             subtítulos quemados     métricas · errores · export
```

Cada sesión es una tarea independiente: **N escenarios = N tareas + N conexiones al modelo**, sin colas centrales ni cambios de código. Detalles en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 🎙️ Fuentes de audio

| tipo | ejemplo | para qué |
|---|---|---|
| `file` | `samples/talk_en.mp3` | probar, re-emitir charlas grabadas, ensayar |
| `stream` | `https://servidor/escenario1.m3u8` | **en vivo**: el audio del escenario (salida de OBS/vMix/cable de audio) |
| `mic` | micrófono de la notebook | un escenario chico / sin mesa de sonido |

```jsonc
// POST /api/sessions  (o desde /admin)
{
  "name": "Escenario A · Keynote",
  "source": { "type": "stream", "url": "https://mi.tv/stage1.m3u8" },
  "src_lang": "en",
  "outputs": ["es", "en"],
  "glossary": ["Nerdearla", "Kubernetes", "Grafana"]
}
```

## 🎥 OBS / vMix

En OBS: **+ Fuente → Navegador (Browser Source)** → URL:

```
https://TU-SERVIDOR/overlay?session=SESION_ID&lang=es&max=3&size=44
```

Fondo transparente, tipografía con sombra, pensado para quemar abajo del stream. Guía completa (incl. vMix) en [`docs/OBS.md`](docs/OBS.md).

## 📈 Escalar a 5, 10 o 30 escenarios

- **Una máquina alcanza para ~10 escenarios**: son 10 tareas asyncio; con Gemini son 10 WebSockets (peso casi nulo en tu servidor); con whisper local hay **un solo modelo compartido en RAM** y el CPU manda (ver tabla de capacidad en [`docs/DEPLOY.md`](docs/DEPLOY.md)).
- **Más escala**: `docker compose up --scale charlaviva=3` detrás de un balanceador que rutée por `session_id` (cada sesión vive en un solo proceso; los espectadores de una misma sesión caen juntos).
- **Costos**: Gemini Live cobra por minuto de audio; whisper local cobra $0 (solo hardware). Presupuesto para 30 sesiones de 45 min en [`docs/DEPLOY.md`](docs/DEPLOY.md).

## 🧪 Tests

```bash
python -m pytest tests/     # parser de captions, export SRT/VTT, 2 sesiones en paralelo
```

## 🗺️ Roadmap

- [x] Transcripción + traducción EN↔ES en vivo, multi-sesión, web + overlay + panel
- [x] Export SRT/VTT/TXT · glosario · fuentes file/stream/mic
- [ ] Portugugués de origen (ya funciona como destino y con `src_lang: pt`)
- [ ] Redis pub/sub para fan-out multi-nodo
- [ ] Corrección humana sobre la marcha (panel de producción)
- [ ] Interpretes humanos + IA como fallback combinado

## 📜 Licencia

[MIT](LICENSE) — cualquier conferencia del mundo puede desplegarla, adaptarla y forkearla.

---

# 🇬🇧 English

**CharlaViva** is open source **live captions & simultaneous translation** for conferences. Feed it live stage audio (browser mic, audio file or HLS/RTMP stream) and it produces **real-time subtitles** in the original language **plus Spanish/English translation** for **many concurrent sessions** (5, 10, 30+ stages). Built for Nerdearla's problem: 30+ English sessions running in parallel, where commercial captioning doesn't scale.

**60-second start:**

```bash
pip install -r requirements.txt
python -m charlaviva demo     # 2 sample stages captioning live
# open http://localhost:8000 — audience view (pick session + language)
```

- **Audience view** (`/`): choose a session and language (original / ES / EN), partial + final captions, bilingual mode, latency badge, SRT/VTT/TXT export. Works on phones.
- **Production panel** (`/admin`): create sessions (file/stream/mic), monitor state, latency percentiles and errors per stage.
- **OBS overlay** (`/overlay?session=ID&lang=es`): transparent burned-in subtitles for your stream ([guide](docs/OBS.md)).
- **Engines**: `gemini` (Gemini Live — best quality, real EN↔ES translation, free tier key), `whisper` (100 % offline ASR via faster-whisper), `canned` (zero-setup fallback). Auto-selection via `CHARLAVIVA_ENGINE=auto`.
- **Scaling**: each stage is an independent asyncio task + one model connection; a single node handles ~10 stages, more via `docker compose up --scale` with session-sticky load balancing ([details](docs/DEPLOY.md)).
- **Test audio included** in [`samples/`](samples/README.md), plus `scripts/fetch_talk.sh` to pull any real talk from YouTube.

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · Deployment & capacity: [`docs/DEPLOY.md`](docs/DEPLOY.md) · Demo video shot-list: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)

License: **MIT**.
