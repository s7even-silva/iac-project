# Checklist: extraer espectros reales (OLTARIS: BON2020 + Historical SPE)

Guía para no tener que volver a correr las herramientas por falta de un dato. Guarda todo en `geant4/GCR_SEP_Sim/data/sources/oltaris/raw_exports/` (crear la carpeta si no existe) antes de reformatear a CSV.

**Cambio de plan (2026-09-08):** se aprobó el acceso a OLTARIS. Reemplaza el plan intermedio con SPENVIS (ISO-15390 para GCR, ESP-PSYCHIC para SEP) — `data/sources/spenvis/` se conserva como plan B, no se borra. Modelos activos ahora: **Badhwar-O'Neill 2020** para GCR, **evento histórico** para SEP (no el modelo probabilístico ESP-PSYCHIC). Ver la carpeta [`data/sources/oltaris/README.md`](../data/sources/oltaris/README.md) para el detalle técnico de cómo activar esta fuente una vez llena.

**Por qué importa anotar todo esto:** vamos a necesitar los mismos datos más adelante para (a) calcular los pesos por bin de energía (`W[s,i]`, ver `ActiveShield_Sim/docs/modelo_realista.md`), (b) la normalización a dosis absoluta en `RunAction.cc`, y (c) la sección de Métodos del artículo — si falta una unidad o un supuesto, hay que volver a entrar a la herramienta.

Herramienta: https://oltaris.larc.nasa.gov/

**Nota sobre el formato ahora que se decidió simular por bins (no muestreo continuo):** pide la tabla **lo más granular posible** (muchos puntos de energía), no una curva suavizada — se va a integrar numéricamente sobre los bordes de bin que se definan después, y cuantos más puntos tenga la tabla original, más precisa sale esa integración.

**⚠️ Cambio de prioridad (2026-09-08): por ahora solo exportar los casos de dosis más alta por especie.** Se prioriza simular primero las condiciones más severas — **GCR en mínimo solar** (ahí el flujo GCR es más alto, ver README.md) y **SEP en el evento máximo (Oct 1989)** — en vez de los 4 casos completos. Eso significa exportar **3 archivos, no 6**: H-mínimo y He-mínimo de GCR, y proton-Oct1989 de SEP. Las secciones de **GCR máximo** y **SEP mínimo (Feb 1956)** quedan marcadas como "diferido" más abajo — se completan después si hay tiempo, no se necesitan para la primera corrida de producción.

---

## Parte 1 — GCR (Environment Definition: GCR, Free Space 1AU)

**Prioridad ahora: solo mínimo solar** (flujo GCR más alto, ver README.md sección "Fechas de referencia"). Máximo solar queda diferido — instrucciones idénticas, solo cambia la fecha, ver nota al final de esta parte.

**✅ Completado (2026-09-08).** Verificado parseando los `.dat` crudos (el
export siempre trae la plantilla genérica de 59 especies, pero el dato real
de la corrida cae en el índice = Z del ion pedido con "Select Specific Ion"
— confirmado con captura de pantalla del selector "Select Nucleus [Z]"):

- [x] GCR Model: **Badhwar-O'Neill 2020**.
- [x] **"Select Specific Ion"** marcado — una corrida para **H** (Z=1, dato real en índice 1 "proton") y otra para **He** (Z=2, dato real en índice 2 — la plantilla lo etiqueta "deuteron" pero es Helio real, ver nota de índice-por-Z arriba).
- [x] Defined by: **Date** (no "Historical Solar Min/Max").
- [x] Fecha para **mínimo solar**: **31/12/2019 – 01/01/2020**.
- [x] **"Mission duration in days" = 1**. Resuelto: no cambia este export — el `.dat` de He con duración 1 día salió idéntico, cifra por cifra, al export anterior con otra duración. Consistente con que la unidad ya es un *flujo por día* (no una fluencia acumulada de la misión) — el campo probablemente solo afecta outputs de dosis/fluencia acumulada que no usamos aquí.
- [x] **"Save external differential flux for space environment?" = Sí**.
- [x] Pantalla de Geometry/Response Functions: sin marcar ninguna Response Function, geometría mínima para dejar correr.
- [x] Cantidad exportada: **flujo diferencial** (`Boundary Flux`, no integral).
- [x] **Unidades**: `particles/((EU*-day-cm2))`, EU* = MeV/amu (H y He no son fotón/electrón/positrón).
- [x] Rango de energía exportado: **1.000000E-02 a 1.000000E+06 MeV/amu**, 125 puntos.
- [x] Archivos reformateados en `data/sources/oltaris/`:
  - `gcr_proton_solarmin.csv`
  - `gcr_alpha_solarmin.csv`
  - Crudos (con nota de dónde está el detalle completo) en `data/sources/oltaris/raw_exports/oltaris_BON2020_{H,He}_solarmin_raw.txt`.
- [x] Captura de pantalla de la configuración (resumen de proyecto de OLTARIS, más confiable que la pantalla de input porque es lo que OLTARIS registró como corrido). Transcrito aquí para no depender de la imagen:
  - Proyecto H: `GCR, Free Space 1AU · GCR Model: BO-20 · Dates: December 31, 2019 to January 1, 2020 · Mission Duration: 1.0 days · Specific ion: Hydrogen [Z=1] · Geometry: zero sphere (42 rays, density-based) · Responses: none`.
  - Proyecto He: idéntico al de H salvo `Specific ion: Helium [Z=2]`.

**Diferido — GCR máximo solar (no hace falta para la primera corrida):** cuando se retome, repetir exactamente los mismos pasos con fecha de **enero 2024** (o cualquiera dentro de 2024-2025) en vez de dic 2019/ene 2020, generando `oltaris_BON2020_H_solarmax.csv` / `oltaris_BON2020_He_solarmax.csv`.

---

## Parte 2 — SEP (Environment Definition: SPE, Free Space 1AU)

**Prioridad ahora: solo el evento máximo (Oct 1989)** — es el caso de mayor dosis, ver README.md. El evento mínimo (Feb 1956) queda diferido, ver nota al final de esta parte.

**A diferencia de GCR, aquí no hay un selector "max/min" simétrico** — OLTARIS ofrece un catálogo de eventos históricos puntuales bajo "Historical SPE", cada uno seleccionable con checkbox + factor de multiplicación (dejar en 1.0). Máximo y mínimo son **dos eventos distintos**, no el mismo evento con distinta fase:

| Fase | Evento elegido | Por qué |
|---|---|---|
| **Máximo (prioridad ahora)** | **Octubre 1989** (checkbox "Oct 1989") | Peor caso estándar en el rango 5-100 MeV (el mismo que usa CREME-96 como referencia); ~4-19×10⁹ p/cm² >30 MeV según la fuente. |
| **Mínimo (diferido)** | **Febrero 1956, ajuste LaRC** (checkbox "Feb 1956 (LaRC)") | El más pequeño de los eventos catalogados en OLTARIS con dato comparable, ~1×10⁹ p/cm² >30 MeV — 5 a 20 veces menor que los demás. Se descartó usar "sin evento" para el mínimo: da dosis ≈0 y anula la comparación de efectividad del campo magnético para ese cuarto de la matriz de escenarios (campo×posición no tendría nada que atenuar). |

Notas sobre la elección:
- Marcar **un solo evento por corrida** (no combinar varios checkboxes) — más simple de citar en Métodos.
- Hay dos ajustes distintos para Feb 1956 (Webber y LaRC) — se eligió **LaRC**, anotarlo así en Métodos.
- Carrington 1859 (las dos opciones "hard fit"/"soft fit") es el evento más grande de la lista, pero es una reconstrucción por proxies (no medido directamente) — no se usa aquí, se dejó como referencia de extremo superior si en algún momento se quiere una tercera comparación.

### ⚠️ Paso crítico, fácil de pasar por alto

En la pantalla **"Environment Definition: SPE, Free Space 1AU"**, el campo **"Save external differential flux for space environment?" está en "No" por defecto — cambiarlo a "Sí".** Ese toggle es lo que exporta el **espectro incidente crudo** que necesitamos.

**No usar** el checkbox "Differential Flux/Fluence" de la siguiente pantalla ("Geometry" / "Response Functions") como fuente del CSV — ese es el flujo **después** de atravesar el blindaje slab/esfera que se configure ahí mismo en OLTARIS. Usarlo aplicaría blindaje dos veces (una vez en OLTARIS, otra en nuestro propio Geant4). En esa pantalla no hace falta marcar nada en particular — cualquier geometría mínima (ej. Slab) alcanza para que el sistema deje correr y exportar.

**✅ Completado (2026-09-08).**

- [x] Corrida **"SEP máximo"** (Oct 1989): "Save external differential flux" = **Sí**. Exportado.
- [x] Especie exportada: **protón** confirmado — es la única con datos reales (índice 1 del `.dat`); neutron/deuteron/triton/helion/alpha vienen todos en `1e-20` (sin dato).
- [x] **Unidades**: `Boundary Fluence`, `particles/((EU*-cm2))`, EU*=MeV (protón) — es una **fluencia** de evento puntual, no un flujo por tiempo (consistente con la fórmula de dosis SEP sin factor de tiempo).
- [x] Rango de energía exportado: **1.000000E-02 a 2.500000E+03 MeV**, 100 puntos.
- [x] Archivo reformateado en `data/sources/oltaris/sep_proton_solarmax.csv`; crudo (con nota de dónde está el detalle completo) en `data/sources/oltaris/raw_exports/oltaris_SPE_oct1989_proton_raw.txt`.
- [x] Captura de pantalla de la configuración (resumen de proyecto de OLTARIS). Transcrito: `SPE, Free Space 1AU · SPE: Oct 1989 multiplier=1.0 · Geometry: zero sphere (42 rays, density-based) · Responses: none` (Proyecto "SEP_max_1989").

**Diferido — SEP mínimo (no hace falta para la primera corrida):** cuando se retome, repetir los mismos pasos marcando **"Feb 1956 (LaRC)"** en vez de "Oct 1989", generando `oltaris_SPE_feb1956_LaRC_proton.csv`.

Con un evento histórico puntual, la interpretación de dosis sigue siendo **dosis aguda de un evento**, sin factor de tiempo — consistente con la fórmula ya anotada en `AGENTS.md`: `dosis_Gy_del_evento = dosis_sim × (fluencia_evento × área_fuente) / N`.

---

## Al terminar (por ahora, los 3 archivos prioritarios)

**✅ Los 3 archivos prioritarios ya están reformateados y en el repo** (2026-09-08):
`data/sources/oltaris/gcr_proton_solarmin.csv`, `gcr_alpha_solarmin.csv`,
`sep_proton_solarmax.csv` (crudos correspondientes en `raw_exports/`).
Pendiente aún:

1. ~~Reformateo de los exports crudos a CSV~~ — hecho.
2. El cálculo de los pesos por bin (`W[s,i]`) a partir de estos espectros, una vez que se fijen los bordes de bin (puntos 6-7 de la lista de pendientes).
3. La normalización a dosis absoluta en `RunAction.cc`/el pipeline de `ActiveShield_Sim`, usando las unidades ya confirmadas arriba (flujo/día para GCR, fluencia de evento para SEP).
4. El párrafo de Métodos describiendo exactamente qué modelo (BON2020, fecha 31/12/2019-01/01/2020 de mínimo solar; evento Oct 1989 de SEP), y qué unidades se usaron — dejando explícito que por ahora se prioriza el caso de mayor dosis por especie, y que GCR máximo/SEP mínimo quedan pendientes de completar.
5. ~~Capturas de pantalla de la configuración de OLTARIS~~ — hecho (resumen de proyecto transcrito en cada parte de este checklist).
6. Decidir si `run_sweep.py`/`select_spectrum_source.py` corren solo el subconjunto GCR-mínimo + SEP-máximo (70 combinaciones) o si se completan los 3 archivos "diferidos" (GCR máximo, SEP mínimo) antes de correr el barrido completo de 140 — hoy `select_spectrum_source.py oltaris` sin `--only` fallaría porque esos 3 archivos aún no existen en `data/sources/oltaris/`.
