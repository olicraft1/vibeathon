# Deploy & escala · Deployment & scaling

## Producción en 3 comandos

```bash
cp .env.example .env      # GEMINI_API_KEY=…  (recomendado)
docker compose up --build -d
# panel:   http://TU-SERVIDOR/admin
```

Sin Docker:

```bash
pip install -r requirements.txt
python -m charlaviva serve --host 0.0.0.0 --port 8000
```

## Cuántos escenarios entran en una máquina

Cada sesión = 1 tarea asyncio + 1 conexión al motor.

**Motor gemini** (recomendado para eventos): el ASR corre en Google, tu servidor
solo mueve WebSockets. Un nodo chico (2 vCPU / 2 GB) lleva **30+ sesiones** sin
despeinarse. El cuello de botella real es la cuota de la API.

**Motor whisper** (100 % local): un único modelo se comparte en RAM entre todas
las sesiones. Regla práctica con `WHISPER_MODEL=small` en CPU (int8, medido en
una instancia moderna):

| CPU | sesiones en tiempo real (parciales ~3.5 s) |
|---|---|
| 4 vCPU | 2–3 |
| 8 vCPU | 5–8 |
| 16 vCPU | 10–15 |

`WHISPER_MODEL=tiny` multiplica la capacidad ×3 (calidad de borrador);
`WHISPER_DEVICE=cuda` con una GPU modesta lleva 20+ escenarios con `small`.
Los parciales son *best effort*: si el CPU satura, se saltean parciales pero los
finales salen igual (la sesión nunca se cae por carga).

## Escalar a más nodos

Las sesiones son independientes; el estado vive en el proceso. Para más escenarios:

```bash
docker compose up --build -d --scale charlaviva=3
```

y poné delante un balanceador que rutée **por `session_id`** (cookie o path
rewrite `/s/{sid}/…` → shard `hash(sid) % 3`): los espectadores de un escenario
siempre caen en el shard dueño de esa sesión. nginx mínimo:

```nginx
upstream charlaviva_shards {
    hash $arg_session_id consistent;
    server 127.0.0.1:8001; server 127.0.0.1:8002; server 127.0.0.1:8003;
}
```

(los WebSockets pasan igual con `proxy_http_version 1.1` +
`proxy_set_header Upgrade/Connection`).

Multi-nodo con fan-out global (cualquier réplica sirve cualquier sesión) es el
próximo paso natural: publicar los `CaptionEvent` en Redis pub/sub y que cada
réplica reenvíe a sus WebSockets. Está en el roadmap.

## Costos (orden de magnitud, sep 2026)

| motor | 30 sesiones × 45 min |
|---|---|
| gemini | ~22 h de audio → revisar precios vigentes de Live API; la capa gratuita cubre demos y pruebas |
| whisper local | $0 de API — solo el hardware de la tabla de arriba |

## Operación durante el evento

- **/admin** es la consola de producción: crear/parar sesiones, ver latencia
  p50/p90 y errores en vivo, links de export y overlay por escenario.
- `GET /api/health` para monitoreo externo (uptime checks, smoke).
- `GET /api/sessions/{id}/metrics` para scrapers (latencias, finals/min).
- Logs por stdout (`docker compose logs -f`). Las sesiones nunca tiran abajo el
  proceso: un motor que falla se reporta en su fila y el resto sigue.
- Al terminar cada charla: `/api/sessions/{id}/export?format=srt&lang=es` — el
  equipo de contenidos recibe el SRT/VTT/TXT ya alineado.

## Checklist pre-evento

- [ ] `python -m charlaviva doctor` en verde
- [ ] `GEMINI_API_KEY` con cuota suficiente (o `WHISPER_MODEL=small` probado en la máquina real)
- [ ] Un stream de prueba por escenario creado en `/admin` con su **glosario** (nombres de speakers, productos)
- [ ] Browser source de OBS apuntando a `/overlay` de cada escenario
- [ ] `samples/` reemplazados o acompañados por el audio de la prueba de sonido de cada sala
