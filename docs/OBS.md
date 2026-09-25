# Subtítulos en el stream · OBS & vMix

CharlaViva incluye una página de overlay transparente pensada para **quemar**
los subtítulos en el stream del escenario.

## OBS Studio

1. Levantá CharlaViva (`python -m charlaviva demo` o `serve`) y creá las
   sesiones desde `/admin` (una por escenario).
2. Copiá el id de la sesión (en la tabla de `/admin está el link 🎥 overlay).
3. En OBS: **+ Fuente → Navegador** (Browser Source):

| campo | valor |
|---|---|
| URL | `http://TU-SERVIDOR/overlay?session=SESION_ID&lang=es&max=3&size=44` |
| Ancho | 1920 |
| Alto | 1080 |
| ☑ Fondo transparente | sí (viene por defecto) |

4. Posicionalo abajo (o arriba con `&pos=top`) sobre el video del escenario.

### Parámetros

| param | default | qué hace |
|---|---|---|
| `session` | — | id de la sesión (obligatorio) |
| `lang` | `es` | idioma de los subtítulos: `es`, `en`, `pt`… |
| `bilingual` | `0` | `1` muestra original + traducción |
| `max` | `3` | líneas finales en pantalla |
| `size` | `40` | tamaño de fuente (px) |
| `pos` | `bottom` | `top` ancla arriba |

Un escenario con dos idiomas = dos Browser Sources (o uno `bilingual=1`).

## vMix

**Add Input → Browser Source** → misma URL. El fondo es transparente, así que
queda superpuesto al video del escenario como cualquier lower-third. vMix GT
también puede tomar los datos crudos por WebSocket (`/ws/captions/{id}`) si
querés un diseño propio.

## Composición típica de Nerdearla

```
┌─────────────────────────────────────┐
│  cámara / slides del escenario       │
│                                     │
│                                     │
│  ┌───────────────────────────────┐  │
│  │ subtítulos CharlaViva (es)    │  │  ← /overlay?lang=es
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
     + stream de audio del escenario ──▶ sesión CharlaViva (fuente "stream")
```

Tip: si el escenario ya manda su audio por HLS/m3u8 hacia el CDN, creá la
sesión con `{"type": "stream", "url": "…"}` y ni siquiera hace falta una
máquina en la sala.
