# Fuente activa: OLTARIS (2026-09-08)

**Estado (2026-09-10): 5 de 6 archivos listos** — `gcr_proton_solarmin.csv`,
`gcr_alpha_solarmin.csv` (fecha 31/12/2019-01/01/2020), `gcr_proton_solarmax.csv`,
`gcr_alpha_solarmax.csv` (fecha 14-15/01/2023 — **no** el pico real del ciclo 25,
ver limitación de BON2020 abajo) y `sep_proton_solarmax.csv` (evento Oct 1989)
ya están reformateados y verificados en esta carpeta. Solo falta
`sep_proton_solarmin.csv` (evento Feb 1956, LaRC) — ver
`../../docs/checklist_espectros_reales.md`. Mientras falte, activar esta
fuente con `select_spectrum_source.py oltaris` (sin `--only`) fallará; usar
`--only gcr_proton_solarmin.csv gcr_alpha_solarmin.csv gcr_proton_solarmax.csv gcr_alpha_solarmax.csv sep_proton_solarmax.csv`
para correr todo excepto SEP mínimo.

**Limitación de fecha descubierta para GCR máximo:** BON2020 en OLTARIS no
acepta fechas más allá de enero de 2023 — no se pudo usar la ventana real del
máximo del ciclo 25 (ene 2024–jul 2025, según NOAA/SWPC) como estaba planeado.
Se usó la fecha más tardía disponible (14-15/01/2023) como mejor aproximación.
Dejar esto explícito en Métodos: la fecha de "máximo" está acotada por la
herramienta, no es el pico real de actividad solar.

Reemplaza a `spenvis/` (ISO-15390 + ESP-PSYCHIC) como fuente de GCR y SEP,
al aprobarse el acceso a la cuenta de OLTARIS. `spenvis/` se conserva como
plan B, no se borra.

## GCR: Badhwar-O'Neill 2020, periodos históricos de mínimo/máximo solar

Ambiente **Free Space**, modelo **BON2020**. A diferencia de ISO-15390 en
SPENVIS (que pedía una fecha puntual), OLTARIS ofrece directamente el
selector de periodo histórico de mínimo/máximo solar.

- `gcr_proton_solarmax.csv`, `gcr_proton_solarmin.csv` (especie H, Z=1)
- `gcr_alpha_solarmax.csv`, `gcr_alpha_solarmin.csv` (especie He, Z=2)

## SEP: evento histórico, no el modelo probabilístico ESP-PSYCHIC

**Máximo y mínimo son dos eventos históricos distintos** (a diferencia del
plan anterior con Oct-1989 duplicado para ambos) — elegidos por fluencia
>30 MeV, ver la comparación completa en
`../../docs/checklist_espectros_reales.md`:

- **Máximo = octubre de 1989** (peor caso estándar en el rango 5-100 MeV,
  ~4-19×10⁹ p/cm² >30 MeV según la fuente).
- **Mínimo = febrero de 1956, ajuste LaRC** (el más pequeño de los eventos
  catalogados en OLTARIS con dato comparable, ~1×10⁹ p/cm² >30 MeV — se
  descartó usar "sin evento" para el mínimo porque da dosis ≈0 y anula la
  comparación de efectividad del campo magnético para ese cuarto de la
  matriz de escenarios).

Ambos son eventos puntuales medidos/reconstruidos, igual que Oct-1989 en el
plan anterior — la fórmula de normalización de dosis para SEP ya diseñada
en `AGENTS.md` (`dosis_Gy_del_evento = dosis_sim × (fluencia_evento × área_fuente) / N`,
sin factor de tiempo) sigue aplicando sin cambios conceptuales.

- `sep_proton_solarmax.csv` (evento Oct 1989)
- `sep_proton_solarmin.csv` (evento Feb 1956, ajuste LaRC)

## Paso crítico al exportar de OLTARIS (SEP)

En la pantalla "Environment Definition: SPE, Free Space 1AU", el toggle
**"Save external differential flux for space environment?" debe estar en
"Sí"**. Ese es el espectro incidente crudo que necesitamos. El checkbox
"Differential Flux/Fluence" de la pantalla de Geometry/Response Functions
es otra cosa — es el flujo **después** de atravesar el blindaje slab/esfera
que se configure ahí mismo en OLTARIS (aplicaría blindaje dos veces si lo
usamos: una vez en OLTARIS, otra en nuestro Geant4). No usar ese checkbox
como fuente del CSV.

## Formato esperado por `SpectrumSampler`

Igual que `spenvis/`: CSV de dos columnas (energía, flujo diferencial),
separador coma o espacio, líneas `#` como comentario. El piloto solo usa la
*forma* de la distribución; las unidades exactas se anotan en el checklist
para la normalización de dosis absoluta (`RunAction.cc`, pendiente).

## Cómo activar esta fuente hoy (5 de 6 archivos)

Desde `geant4/GCR_SEP_Sim/`, mientras falte `sep_proton_solarmin.csv`:

    python3 scripts/select_spectrum_source.py oltaris --only gcr_proton_solarmin.csv gcr_alpha_solarmin.csv gcr_proton_solarmax.csv gcr_alpha_solarmax.csv sep_proton_solarmax.csv

Una vez que los 6 estén reales, se podrá correr `select_spectrum_source.py oltaris`
sin `--only`. Después de activar la fuente, volver a correr `cmake ..` dentro
de `build/` (no basta con `make -j`) para que el binario recoja los CSV
actualizados.

## Checklist de qué anotar al exportar

Ver `docs/checklist_espectros_reales.md` (ya actualizado para OLTARIS) —
por cada uno de los 6 archivos: especie, unidades exactas, rango de
energía, y captura de pantalla de la configuración usada.
