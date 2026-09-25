# Sample talks

Bundled test audio so CharlaViva can be tried in one command, with zero setup:

| file | language | duration | contents |
|---|---|---|---|
| `talk_en.mp3` | English | 84 s | "Scaling Open Source" — has Kubernetes, GitHub Actions, Prometheus, Grafana |
| `talk_en2.mp3` | English | 42 s | "Why Postgres" lightening talk |
| `talk_es.mp3` | Spanish | 65 s | "Accesibilidad en conferencias" (EN translation included) |

- The audio was **synthesized with text-to-speech** for this repository (so the
  repo ships no third-party recordings). Each file has a sibling
  `*.mp3.cues.json` with the pre-authored captions used by the `canned`
  fallback engine.
- To demo with **real conference audio**, pull any Nerdearla talk from YouTube:
  `./scripts/fetch_talk.sh "https://www.youtube.com/watch?v=…"` and create a
  session pointing at the downloaded file.
