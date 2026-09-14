# Dashboard del barrido distribuido — implementado (2026-09-14)

Contexto: el coordinator (`https://coordinator.vlaboratory.org`, FastAPI +
SQLite, ver AGENTS.md "Cómputo distribuido") ya exponía todo el dato crudo
necesario por HTTP (`/api/v1/health`, `/api/v1/jobs`, `/api/v1/workers`).
Este documento describe el dashboard de solo lectura ya construido sobre
esos endpoints, y por qué terminó sirviéndose desde el propio coordinator
en vez de como Artifact de Claude (plan original, descartado — ver abajo).

## Cambio de diseño: por qué no es un Artifact

El plan original proponía un Artifact de Claude Code haciendo `fetch()`
directo desde el navegador del visitante hacia
`coordinator.vlaboratory.org`, con CORS agregado en el coordinator como
único cambio de backend. **Se implementó así y no funcionó**: el sandbox
donde corre un Artifact aplica una Content-Security-Policy que solo admite
conexiones (`fetch`/XHR) hacia un allowlist fijo de CDNs (cdnjs, jsdelivr,
fonts.googleapis) — un dominio propio como `coordinator.vlaboratory.org`
nunca pasa esa lista, sin importar qué cabeceras CORS mande el servidor.
El error real en consola: `Refused to connect because it violates the
document's Content Security Policy` — no es un error de CORS (que sí se
había verificado y funcionaba), es la CSP del sandbox bloqueando la
conexión antes de que la petición salga del navegador.

**Esto no se verificó antes de diseñar sobre esa base** — la suposición de
que un Artifact podía hacer `fetch()` cross-origin libre, como cualquier
página web servida normalmente, resultó incorrecta para este entorno
específico. Ninguna combinación de cabeceras del lado del servidor lo
arregla.

**Solución adoptada:** el propio coordinator sirve el dashboard como
página estática en `GET /dashboard` (mismo origen que `/api/v1/*`, sin
CORS ni CSP cross-origin de por medio). El middleware `CORSMiddleware`
agregado en el primer intento se quitó — no cumple ningún propósito una
vez que el dashboard es same-origin, y menos superficie expuesta es mejor
dado el riesgo ya aceptado de "sin autenticación de workers" (ver
AGENTS.md). `/dashboard` se agregó a `_PUBLIC_PATHS` (mismo criterio que
`/api/v1/health`) para que siga siendo accesible aunque `WORKER_TOKEN` se
active más adelante.

## Qué se conserva del plan original

- **Solo lectura**, sin ningún botón de escritura (pausar worker,
  reencolar job, etc.) — el dashboard nunca llama a ningún endpoint
  `POST`/`PATCH` del coordinator.
- **Rama `infra/distributed-sweep`** misma, sin rama nueva.
- **Filtros de cliente** (status/species/repetición/worker asignado), sin
  ida y vuelta al servidor — con ~600 jobs esto sigue siendo viable
  cargando todo de una vez.
- **Actualización bajo demanda** (botón "Actualizar"), no `setInterval` —
  sigue siendo una mejora opcional posterior, no parte de este corte.

## Dónde vive

- `infra/coordinator/dashboard.html` — la página completa (HTML+CSS+JS
  vanilla, sin build, sin dependencias de npm; solo Google Fonts vía
  `<link>`, dentro del allowlist normal de un navegador — esto ya no
  corre en un sandbox de Artifact, así que esa restricción no aplica
  aquí).
- `infra/coordinator/app.py`, ruta `GET /dashboard` — sirve ese archivo
  con `FileResponse`.

Acceso: `https://coordinator.vlaboratory.org/dashboard` una vez
desplegado el cambio a la VM (mismo procedimiento de siempre: `git
fetch`+`reset --hard` en `/opt/iac-project` corriendo como el usuario
`coordinator`, `systemctl restart geant4-coordinator`).

## Qué muestra

1. Tarjetas de resumen (`pending`/`running`/`done`/`failed`, workers
   online) desde `/api/v1/health`.
2. Tabla de **workers**: estado online/offline (calculado por el
   coordinator con su propio reloj, ver `seconds_since_heartbeat`/`online`
   en `app.py`), núcleos, RAM libre/total, carga de CPU, `cpu_score`,
   digest de imagen truncado.
3. Tabla de **jobs** con filtros por estado, especie, repetición, y
   búsqueda de texto libre sobre el worker asignado (cruza `claimed_by`
   contra la tabla de workers para mostrar el label, no el UUID crudo).
   Click en una fila expande el detalle (bin, offset, intentos,
   `last_error` si `failed`, timestamps).

## Fuera de alcance (sin cambios respecto al plan original)

- Cualquier acción de escritura desde el dashboard.
- Gráficas históricas/series de tiempo — el coordinator no trackea eso
  hoy.
- Autenticación del dashboard en sí — es de solo lectura sobre datos ya
  públicos sin auth (mismo riesgo aceptado que el resto de la API, ver
  AGENTS.md).

## Mejora opcional futura

Actualización en vivo: un `setInterval` cada 30-60s repitiendo los mismos
3 `fetch()` y re-renderizando — mismo patrón que ya usa el propio worker
para su heartbeat, no amerita WebSockets/SSE dado el volumen y frecuencia
de datos. No implementado a propósito en este corte.
