# Guía del video demo · Demo video shot-list (1–2 min)

Objetivo: que el jurado vea el proyecto **funcionando con audio real de una
charla** y entienda cómo se usa, en menos de dos minutos.

## Preparación (5 minutos antes de grabar)

1. `pip install -r requirements.txt && python -m charlaviva doctor`
2. La forma más rápida: **`./scripts/demo_real_talks.sh`** — baja el audio de 3
   charlas reales de Nerdearla (YouTube), levanta CharlaViva con Gemini Live y
   crea una sesión por charla. Necesitás `export GEMINI_API_KEY=…`.
   (Manual: `./scripts/fetch_talk.sh "<url>"` y creá las sesiones en `/admin`.)
3. Dejá abiertos: una pestaña en `/` (audiencia), `/admin`, y OBS con el overlay.

## Guion sugerido (90 s)

| # | plano | narración (30–40 palabras por pantalla) |
|---|---|---|
| 1 | pantalla completa del logo + `/` | "CharlaViva: subtítulos simultáneos open source para conferencias. Audio en vivo → transcripción original + traducción EN↔ES en tiempo real." |
| 2 | click en la sesión del Keynote (EN) | "Elegís el escenario y el idioma. Mirá los subtítulos parciales mientras hablan y los finales al cerrar la idea — menos de dos segundos de latencia." |
| 3 | pestaña Español + modo bilingüe | "La audiencia elige: original, español, o los dos juntos. Funciona en el celular, sin instalar nada." |
| 4 | `/admin` con las 2 sesiones corriendo | "Producción ve todas las salas en simultáneo: estado, latencia, errores. Estas son dos sesiones al mismo tiempo; el mismo nodo lleva diez." |
| 5 | OBS con el overlay quemado | "Los mismos subtítulos se queman en el stream con un Browser Source de OBS — cero software nuevo para la regiduría." |
| 6 | click Export → SRT abierto en un editor | "Y al terminar la charla, exportás la transcripción completa: SRT, VTT o texto, en el idioma que quieras." |

Cierra con: "MIT license, deploy en un comando — cualquier conferencia open
source puede usarlo."

## Pro-tip del brief 🏆

> *"Si te animás, agregá los subtítulos en inglés hechos con tu propio proyecto"*

Hacelo en serio: grabá la narración **en español**, corre ese audio por
CharlaViva (sesión `mic` o archivo) y exportá el **VTT en inglés**; subilo como
pistas de subtítulos del propio video en YouTube. El jurado angloparlante lee tu
proyecto explicándose solo.

## Subida

- YouTube (público o no listado) + link en el form de Devpost.
- En la descripción: link al repo + "0:00 qué es · 0:12 audiencia · 0:35
  producción · 0:50 OBS · 1:05 export".
