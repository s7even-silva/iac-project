# Checklist: extraer espectros reales (Badhwar-O'Neill + SPENVIS ESP-PSYCHIC)

Guía para no tener que volver a correr las herramientas por falta de un dato. Cada persona llena su parte (GCR → OLTARIS, SEP → SPENVIS) y guarda todo en `geant4/GCR_SEP_Sim/data/raw_exports/` (crear la carpeta si no existe) antes de reformatear a CSV.

**Por qué importa anotar todo esto:** vamos a necesitar los mismos datos más adelante para (a) el CSV de `SpectrumSampler`, (b) la normalización a dosis absoluta (Gy/día o Sv/año) en `RunAction.cc`, y (c) la sección de Métodos del artículo — si falta una unidad o un supuesto, hay que volver a entrar a la herramienta.

---

## Parte 1 — GCR con OLTARIS (Badhwar-O'Neill 2020)

Herramienta: https://oltaris.larc.nasa.gov/

- [ ] Cuenta creada / acceso confirmado.
- [ ] Ambiente creado: tipo **Free Space**, modelo GCR = **Badhwar-O'Neill 2020**.
- [ ] **Periodo elegido para "solar mínimo"**: fecha inicio — fin: ______________ (anotar la fecha exacta usada; OLTARIS pide un rango histórico, no solo "min/max" genérico)
- [ ] **Periodo elegido para "solar máximo"**: fecha inicio — fin: ______________
- [ ] Especies exportadas: **H (Z=1)** y **He (Z=2)** por separado (no la suma total) — confirmar que la exportación distingue especies.
- [ ] Cantidad exportada: ¿flujo diferencial (dJ/dE) o integral (J>E)? → anotar cuál: ______________
- [ ] **Unidades exactas** tal como las muestra OLTARIS (ej. `partículas / (cm² · s · sr · MeV/nucleón)`): ______________
- [ ] Rango de energía exportado (MeV/nucleón, min–max): ______________
- [ ] Archivo(s) exportado(s) guardado(s) en `data/raw_exports/` con nombre claro, ej.:
  - `oltaris_BON2020_H_solarmin.csv` (o .txt/.xlsx, lo que exporte la herramienta)
  - `oltaris_BON2020_H_solarmax.csv`
  - `oltaris_BON2020_He_solarmin.csv`
  - `oltaris_BON2020_He_solarmax.csv`
- [ ] Captura de pantalla de la configuración del ambiente (para citar parámetros exactos en Métodos) guardada en `data/raw_exports/oltaris_config_screenshot.png`.

---

## Parte 2 — SEP con SPENVIS (ESP-PSYCHIC)

Herramienta: https://www.spenvis.oma.be/ (registro: https://www.spenvis.oma.be/registration.php)

**Importante:** ESP-PSYCHIC NO tiene un selector directo "solar mínimo/máximo". La fase solar se controla indirectamente vía la **fecha de inicio de misión** (o, en modo avanzado, el parámetro **"offset en el ciclo solar"**), y el modelo tiene dos tipos de salida — **Total Fluence** y **Worst Case Event** — que no son "max/min", son dos formas distintas de reportar severidad (ver más abajo cuál usar).

- [ ] Cuenta creada / acceso confirmado.
- [ ] Modelo corrido: **ESP-PSYCHIC**, protones.
- [ ] Tipo de salida usado: **Worst Case Event** (recomendado — ver nota abajo, no "Total Fluence").
- [ ] **Duración de misión** usada (debe ser la MISMA para la corrida max y la min, para que la comparación sea justa): ______________
- [ ] **Nivel de confianza** elegido (ej. 95% — el modelo es probabilístico, el resultado cambia mucho según esto; debe ser el mismo para max y min): ______________
- [ ] Corrida **"SEP max"**: fecha de inicio de misión / offset de ciclo solar usado (ubicado en fase de **máximo** solar): ______________
- [ ] Corrida **"SEP min"**: fecha de inicio de misión / offset de ciclo solar usado (ubicado en fase de **mínimo** solar): ______________
- [ ] **Unidades exactas** del export (ej. `protones/cm²` por el evento, o `protones/(cm²·MeV)` diferencial): ______________
- [ ] Rango de energía exportado (MeV, min–max): ______________
- [ ] Archivo(s) guardado(s) en `data/raw_exports/`, ej.:
  - `spenvis_ESP-PSYCHIC_proton_solarmin.csv`
  - `spenvis_ESP-PSYCHIC_proton_solarmax.csv`
- [ ] Captura de pantalla de la configuración del modelo (fecha/offset, duración, nivel de confianza) guardada en `data/raw_exports/spenvis_config_screenshot.png` — sin esto no se puede reproducir la corrida si falta un dato.

### ⚠️ Por qué "Worst Case Event" y no "Total Fluence"

Nuestro estudio compara **eventos** de radiación (GCR/SEP máximo y mínimo como severidad instantánea de un evento), no la dosis acumulada de una misión completa de varios años. "Worst Case Event" te da la fluencia de un único evento SEP severo — el equivalente conceptual a "GCR en fase de máximo solar" — mientras que "Total Fluence" suma todos los eventos de toda la misión, que es una pregunta distinta (dosis acumulada de misión larga). Si tienen dudas sobre esto al momento de correrlo, avísenme antes de exportar — cambiar de opinión después implica volver a correr el modelo.

Con "Worst Case Event" la interpretación de dosis queda como **dosis aguda de un evento puntual** (no "por día"), consistente con lo que se anota en `RunAction.cc` — ver `CLAUDE.md`.

---

## Al terminar ambas partes

Avísenme cuando tengan todo esto lleno + los archivos en `data/raw_exports/`, y yo hago:

1. Reformateo de los exports crudos a los 6 CSV que `SpectrumSampler` ya espera (`data/gcr_proton_solarmax.csv`, etc.).
2. La normalización a dosis absoluta en `RunAction.cc`, usando las unidades y la decisión SEP que anotaron arriba.
3. El párrafo de Métodos describiendo exactamente qué modelo, qué periodo/confianza, y qué unidades se usaron (para que quede citable en el artículo).
