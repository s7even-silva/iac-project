# Plan: dashboard del barrido distribuido (Artifact de Claude)

Contexto para quien retome esto: el coordinator (`https://coordinator.vlaboratory.org`,
FastAPI + SQLite, ver AGENTS.md "Cómputo distribuido") ya expone todo el dato
crudo necesario por HTTP. Este plan es solo para **visualizarlo** — no cambia
el diseño del coordinator/worker, salvo un middleware de CORS.

Decisiones ya tomadas (no volver a preguntar):
- **Hosting: Artifact de Claude Code**, no Cloudflare Pages. Más rápido de
  armar y actualizar; se puede migrar a Cloudflare Pages después si hace
  falta el dominio propio, pero no es parte de este plan.
- **Rama: `infra/distributed-sweep` misma**, no una rama nueva. El único
  cambio al coordinator (CORS) es chico y aislado.
- **Solo lectura.** El dashboard nunca escribe al coordinator (no hay botón
  de "pausar worker" ni similar) — evita cualquier necesidad de autenticación
  del lado del dashboard.

## 1. Qué datos ya existen (verificado, no asumido)

`GET /api/v1/jobs` — lista completa (ahora mismo ~600 filas), cada una con:
```
job_id, species, bin_index, offset_x_m, repeticion, n_events, priority,
min_ram_gb, min_cpu_count, min_cpu_score, status, claimed_by, claimed_at,
attempt, max_attempts, last_error, created_at, updated_at
```
`status` es uno de `pending|claimed|running|done|failed`. `claimed_by` es el
`worker_id` (o `null`) — es la clave para saber "qué máquina corre qué job".

`GET /api/v1/workers` — cada worker con:
```
worker_id, hostname, cpu_count, ram_gb, ram_free_gb, cpu_load_pct, label,
registered_at, last_heartbeat, status, cpu_score, image_digest,
seconds_since_heartbeat, online
```
`online` y `seconds_since_heartbeat` ya vienen calculados por el servidor
(ver `app.py`, quinta ronda de revisión) — el dashboard no debe recalcular
esto con su propio reloj, solo leer estos dos campos.

`GET /api/v1/health` — contadores agregados (`jobs_pending`, `jobs_running`,
`jobs_done`, `jobs_failed`, `workers_online`, `stale_job_timeout_s`,
`worker_image_digest`).

Ningún endpoint pagina todavía — `GET /jobs` devuelve todo de una vez. Con
~600 filas hoy esto es aceptable para cargarlo entero en el navegador y
filtrar/ordenar en JS; si el barrido crece mucho más (miles de filas), vale
la pena revisar paginación del lado del servidor antes de que el payload se
vuelva pesado — no es necesario para la primera versión.

## 2. Cambio necesario en el coordinator: CORS

Hoy `GET /api/v1/health` responde bien por `curl` pero **sin** cabecera
`Access-Control-Allow-Origin` (verificado explícitamente: `curl -H "Origin:
https://example.pages.dev" .../health` da `200` pero sin esa cabecera) — un
Artifact corriendo en el navegador del visitante (dominio de claude.ai/
claudeusercontent.com) no podrá leer la API sin esto, aunque `curl` sí pueda.

En `infra/coordinator/app.py`, agregar (después de crear `app = FastAPI(...)`,
antes del middleware de token ya existente):
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # solo lectura, sin cookies/credenciales -- ver nota abajo
    allow_methods=["GET"],
    allow_headers=["*"],
)
```
`allow_origins=["*"]` es aceptable aquí porque (a) todos los endpoints que el
dashboard toca son `GET` de solo lectura, sin datos sensibles más allá de lo
que ya es público sin autenticación (ver "Sin autenticación de workers" en
AGENTS.md, riesgo ya aceptado), y (b) no hay cookies ni credenciales de por
medio. Si más adelante se activa `WORKER_TOKEN`, revisar si el dashboard
necesita seguir funcionando sin él (probablemente sí, para no exponer el
token en el navegador de cualquier visitante — en ese caso, un endpoint de
solo lectura separado sin el middleware de token sería la vía correcta, no
bypasear el token existente).

Verificar tras el cambio: reiniciar el servicio en la VM
(`sudo systemctl restart geant4-coordinator`, mismo procedimiento ya usado
para las migraciones anteriores) y confirmar con:
```bash
curl -sI https://coordinator.vlaboratory.org/api/v1/health -H "Origin: https://claudeusercontent.com" | grep -i access-control
```

## 3. Diseño del Artifact

Una sola página HTML con JS vanilla (sin build, sin dependencias de npm) que:

1. Al cargar, hace `fetch()` a los 3 endpoints (`/health`, `/jobs`, `/workers`)
   directo desde el navegador del visitante hacia
   `https://coordinator.vlaboratory.org` — sin backend propio del Artifact,
   sin proxy.
2. Muestra un resumen arriba (tarjetas: pending/running/done/failed,
   workers online) — datos de `/health`.
3. Una tabla de **workers**: label, `online` (con color: verde si `true`),
   `seconds_since_heartbeat` (formateado legible, ej. "hace 12s"), `cpu_count`,
   `ram_free_gb`/`ram_gb`, `cpu_load_pct`, `cpu_score`, `image_digest`
   (truncado, con tooltip del hash completo) — responde directamente "qué
   máquina corre qué" al cruzarla con la tabla de jobs por `worker_id`.
4. Una tabla de **jobs**, con filtros de cliente (sin ida y vuelta al
   servidor, ya que los datos completos ya están en memoria del navegador):
   - Por `status` (pending/running/done/failed) — probablemente el filtro
     más usado.
   - Por `species` (GCR_H/GCR_He/SEP_p).
   - Por `repeticion` (0-4 hoy).
   - Buscador de texto libre sobre `claimed_by`/label del worker asignado
     (cruzando con la tabla de workers para mostrar el label, no el
     `worker_id` crudo, en la columna "asignado a").
5. Click en una fila de job para expandir detalle (bin_index, offset_x_m,
   n_events, attempt/max_attempts, last_error si `status=failed`,
   created_at/updated_at) — evita saturar la tabla principal con columnas
   que no todos necesitan ver siempre.

### Actualización en vivo

El usuario dijo que no es estrictamente necesario, así que la primera
versión puede ser **solo bajo demanda** (un botón "Actualizar" que repite
los 3 `fetch()`) — más simple, cero costo de mantenimiento, y evita
sorpresas de un `setInterval` corriendo indefinidamente en la pestaña de
cualquiera que la deje abierta.

Si más adelante se quiere ese "en vivo": un `setInterval` cada 30-60s
llamando a los mismos 3 endpoints y re-renderizando (mismo patrón que ya
usa el propio worker para el heartbeat, no hace falta WebSockets ni SSE —
el volumen de datos y la frecuencia no lo justifican). Dejar esto como
mejora opcional posterior, no parte del primer corte.

## 4. Pasos concretos para la sesión que implemente esto

1. Leer `AGENTS.md`, sección "Cómputo distribuido para el barrido de
   ActiveShield_Sim", para el contexto completo del diseño del coordinator
   (por qué el job es una combinación `species/bin_index/offset_x_m/
   repeticion`, qué es `cpu_score`, qué es `image_digest`/auto-actualización).
2. Confirmar el estado real de la cola antes de diseñar contra datos
   viejos: `curl -s https://coordinator.vlaboratory.org/api/v1/health`.
3. Agregar el `CORSMiddleware` en `infra/coordinator/app.py` (sección 2
   arriba). Correr los tests existentes (`infra/coordinator/
   test_coordinator.py`) para confirmar que nada se rompe — un middleware
   de CORS no debería afectar ninguna lógica de negocio, pero verificar.
4. Aplicar el cambio en la VM real (mismo procedimiento ya usado varias
   veces en esta sesión: `git fetch`+`reset --hard` en `/opt/iac-project`,
   `systemctl restart geant4-coordinator`) y verificar la cabecera CORS
   como se indica en la sección 2.
5. Construir el Artifact (HTML+JS+CSS en un solo archivo, sin dependencias
   externas más allá de quizás una fuente de Google Fonts si se quiere,
   ver reglas de diseño de Artifacts) que consuma la API real.
6. Probar en vivo contra el coordinator real antes de dar por terminado —
   confirmar que los filtros funcionan, que las tablas muestran datos
   coherentes con lo que da `curl` directo, y que el botón de actualizar
   funciona.
7. Publicar el Artifact y compartir el link — decidir en esa sesión si
   conviene pin/compartir con el equipo.

## 5. Fuera de alcance de este plan (no implementar salvo que se pida)

- Autenticación del dashboard en sí (es de solo lectura sobre datos ya
  públicos sin auth, ver riesgos aceptados en AGENTS.md).
- Cualquier acción de escritura desde el dashboard (pausar/reencolar un
  job a mano, cambiar `worker_image_digest`, etc.) — eso seguiría
  haciéndose por SSH + los scripts ya existentes (`set_worker_image.py`,
  updates directos a la DB), no desde una UI pública.
- Gráficas históricas/series de tiempo (ej. "jobs completados por hora") —
  el coordinator no guarda ese historial hoy (solo el estado actual de cada
  fila), haría falta agregar tracking de eventos aparte si se quiere esto.
- Migrar a Cloudflare Pages / dominio propio — mencionado por el usuario
  como intención pero explícitamente pospuesto en favor del Artifact para
  la primera versión.
