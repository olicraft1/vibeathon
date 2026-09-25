# Arquitectura · Architecture

CharlaViva convierte audio en vivo de N escenarios en subtítulos multilingües,
con una interfaz para la audiencia, un overlay para el stream y un panel para
producción.

```
                         ┌────────────────────────────────────────────┐
 mic ──┐                 │ charlaviva/server.py  (FastAPI)            │
 file ─┼─▶ sources.py ──▶│  /            audiencia (web)              │
stream─┘   PCM16 16 kHz  │  /admin       producción                   │
              │          │  /overlay     OBS browser source            │
              ▼          │  /api/…       REST                          │
          audio.py VAD   │  /ws/captions  fan-out de eventos           │
              │          │  /ws/audio     ingest de micrófono          │
              ▼          └────────────────────────────────────────────┘
     session.py  (una por escenario)                     ▲
       │  feed()  ·  on_utterance_end() (hybrid VAD)     │ CaptionEvent JSON
       ▼                                                │
     engines/                                           │
       ├── gemini_live.py   Gemini Live API (1 WS/escenario)   [mejor calidad]
       ├── whisper_local.py faster-whisper (modelo compartido) [100 % local]
       ├── mt.py            traducción de texto (Gemini)        [opcional]
       └── canned.py        replay de cues de samples/          [fallback/tests]
```

## Pipeline por sesión

1. **`sources.py`** produce chunks de PCM16 mono @ 16 kHz con su timestamp `t`
   en la línea de tiempo de la sesión (~100 ms). `FileSource` reproduce a
   velocidad real (o `speed` para ensayar), `StreamSource` sigue un stream de
   red, `MicSource` recibe PCM del navegador por WebSocket.
2. **`audio.py · EnergyVAD`** detecta inicio/fin de habla (energía RMS).
   El fin de habla dispara `on_utterance_end()` → *hybrid VAD*: el motor cierra
   la oración sin esperar su propio VAD (baja la latencia).
3. **`engines/`** producen `CaptionEvent`:

```jsonc
{
  "seq": 42,            // orden global de la sesión
  "utt_id": 7,          // id de oración (los partials la actualizan en vivo)
  "kind": "partial",    // partial | final | status
  "texts": {"en": "…", "es": "…"},   // uno por idioma disponible
  "src_lang": "en",
  "t0": 31.2, "t1": 35.9,            // segundos en la línea de tiempo del audio
  "latency_ms": 780,                 // retraso vs. el audio "en vivo"
  "engine": "gemini:gemini-3.8-live"
}
```

4. **`session.py · Session`** agrega historia (los `final`), calcula latencia,
   y hace fan-out a los WebSockets suscriptos (cola con drop-oldest: un cliente
   lento nunca frena al sistema).
5. **Frontends** solo consumen `/ws/captions/{id}`: la vista de audiencia
   renderiza parciales en gris y finales sólidos; el overlay arma una pila de
   líneas transparente; `/admin` muestrea métricas.

## Claves de diseño

- **Un solo formato de audio** (PCM16/16 kHz mono) — exactamente lo que
  `send_realtime_input` de Gemini Live acepta. PyAV decodifica cualquier
  códec/contenedor (mp3, m4a, opus, HLS…) sin ffmpeg del sistema.
- **Interfaz de motor mínima** (`feed`, `on_utterance_end`, `emit`) — agregar un
  motor nuevo (p. ej. un modelo local distinto, o una API de STT comercial para
  comparar) es un archivo de ~100 líneas.
- **Gemini en un solo round-trip por sesión**: el modo `caption` pide al modelo
  líneas etiquetadas (`[en] …`, `[es] …`) = transcripción + traducción en una
  conexión. El parser (`engines/parser.py`) emite parciales por cada delta de
  texto y finales al cerrar bloque. El modo alternativo `transcribe` usa el
  modelo especializado `gemini-3.5-transcribe-live` (mejor ASR) + traducción de
  texto por oración (`engines/mt.py`).
- **Whisper local con modelo único compartido** entre todas las sesiones (clave
  de caché: modelo/dispositivo/presición) y transcripción en `to_thread` para no
  bloquear el event loop.
- **Degradación honesta**: sin API key → whisper; sin modelo descargable →
  `canned` (si el audio trae `*.cues.json`) con un aviso en el estado de la
  sesión; el panel muestra el motor real que está corriendo.

## Presupuesto de latencia (medido en `/admin`)

| etapa | típica |
|---|---|
| chunk + VAD | ~100 ms |
| engine (gemini caption / whisper small) | 300–1500 ms |
| fan-out WebSocket + render | <50 ms |
| **total visible** | **~0.5–2 s** |
