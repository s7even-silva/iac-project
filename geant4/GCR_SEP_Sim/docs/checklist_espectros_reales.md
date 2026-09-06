# Checklist: extraer espectros reales (SPENVIS: ISO-15390 + ESP-PSYCHIC)

Guía para no tener que volver a correr las herramientas por falta de un dato. Cada persona llena su parte (GCR o SEP) y guarda todo en `geant4/GCR_SEP_Sim/data/raw_exports/` (crear la carpeta si no existe) antes de reformatear a CSV.

**Cambio de plan (2026-09-06):** originalmente se iba a usar Badhwar-O'Neill 2020 vía OLTARIS para GCR, pero la cuenta de OLTARIS quedó pendiente de aprobación (sin tiempo estimado) y no hay margen para esperar. Como SPENVIS ya tiene el registro aprobado y activo, **GCR y SEP se sacan ambos de SPENVIS**: GCR con **ISO-15390** (estándar internacional, más moderno que CREME96 — ver conversación previa sobre por qué se descartó CREME96), SEP con **ESP-PSYCHIC** (sin cambios respecto a lo ya definido). Si más adelante se aprueba OLTARIS y quieren agregar Badhwar-O'Neill como comparación adicional, avisen y actualizamos esto — pero no bloqueen el trabajo actual esperándolo.

**Por qué importa anotar todo esto:** vamos a necesitar los mismos datos más adelante para (a) el CSV de `SpectrumSampler`, (b) la normalización a dosis absoluta (Gy/día o Sv/año) en `RunAction.cc`, y (c) la sección de Métodos del artículo — si falta una unidad o un supuesto, hay que volver a entrar a la herramienta.

Ambas partes se hacen en la misma herramienta: https://www.spenvis.oma.be/ (registro: https://www.spenvis.oma.be/registration.php)

---

## Parte 1 — GCR con SPENVIS (ISO-15390)

- [ ] Modelo corrido: **ISO-15390**, GCR.
- [ ] Especies exportadas: **H (Z=1)** y **He (Z=2)** por separado (no la suma total) — el modelo cubre Z=1 a 92, confirmar que la exportación permite bajar cada especie aparte.
- [ ] **Fecha usada para "GCR min"**: **enero 2020** (ver README.md — mínimo solar oficial NASA/NOAA fue diciembre 2019). ISO-15390 en SPENVIS pide una fecha específica que internamente convierte a potencial de modulación solar (Φ) vía el número de manchas solares — no hace falta calcular Φ a mano, solo poner la fecha.
- [ ] **Fecha usada para "GCR max"**: **enero 2024** (ventana de máximo del ciclo 25).
- [ ] Cantidad exportada: ¿flujo diferencial (dJ/dE) o integral (J>E)? → anotar cuál: ______________
- [ ] **Unidades exactas** tal como las muestra SPENVIS (ej. `partículas / (cm² · s · sr · MeV/nucleón)`): ______________
- [ ] Rango de energía exportado (MeV/nucleón, min–max): ______________
- [ ] Archivo(s) exportado(s) guardado(s) en `data/raw_exports/` con nombre claro, ej.:
  - `spenvis_ISO15390_H_solarmin.csv`
  - `spenvis_ISO15390_H_solarmax.csv`
  - `spenvis_ISO15390_He_solarmin.csv`
  - `spenvis_ISO15390_He_solarmax.csv`
- [ ] Captura de pantalla de la configuración del modelo (fecha, especies, rango de energía) guardada en `data/raw_exports/spenvis_iso15390_config_screenshot.png` — sin esto no se puede reproducir la corrida si falta un dato.

---

## Parte 2 — SEP con SPENVIS (ESP-PSYCHIC)

Sin cambios respecto a antes.

**Importante:** ESP-PSYCHIC NO tiene un selector directo "solar mínimo/máximo". La fase solar se controla indirectamente vía la **fecha de inicio de misión** (o, en modo avanzado, el parámetro **"offset en el ciclo solar"**), y el modelo tiene dos tipos de salida — **Total Fluence** y **Worst Case Event** — que no son "max/min", son dos formas distintas de reportar severidad (ver más abajo cuál usar).

- [ ] Modelo corrido: **ESP-PSYCHIC**, protones.
- [ ] Tipo de salida usado: **Worst Case Event** (recomendado — ver nota abajo, no "Total Fluence").
- [ ] **Duración de misión** usada (debe ser la MISMA para la corrida max y la min, para que la comparación sea justa): ______________
- [ ] **Nivel de confianza** elegido (ej. 95% — el modelo es probabilístico, el resultado cambia mucho según esto; debe ser el mismo para max y min): ______________
- [ ] Corrida **"SEP max"**: fecha de inicio de misión / offset de ciclo solar — usar **enero 2024** (misma fecha que GCR max, ver README.md): ______________
- [ ] Corrida **"SEP min"**: fecha de inicio de misión / offset de ciclo solar — usar **enero 2020** (misma fecha que GCR min): ______________
- [ ] **Unidades exactas** del export (ej. `protones/cm²` por el evento, o `protones/(cm²·MeV)` diferencial): ______________
- [ ] Rango de energía exportado (MeV, min–max): ______________
- [ ] Archivo(s) guardado(s) en `data/raw_exports/`, ej.:
  - `spenvis_ESP-PSYCHIC_proton_solarmin.csv`
  - `spenvis_ESP-PSYCHIC_proton_solarmax.csv`
- [ ] Captura de pantalla de la configuración del modelo (fecha/offset, duración, nivel de confianza) guardada en `data/raw_exports/spenvis_esppsychic_config_screenshot.png`.

### ⚠️ Por qué "Worst Case Event" y no "Total Fluence"

Nuestro estudio compara **eventos** de radiación (GCR/SEP máximo y mínimo como severidad instantánea de un evento), no la dosis acumulada de una misión completa de varios años. "Worst Case Event" te da la fluencia de un único evento SEP severo — el equivalente conceptual a "GCR en fase de máximo solar" — mientras que "Total Fluence" suma todos los eventos de toda la misión, que es una pregunta distinta (dosis acumulada de misión larga). Si tienen dudas sobre esto al momento de correrlo, avísenme antes de exportar — cambiar de opinión después implica volver a correr el modelo.

Con "Worst Case Event" la interpretación de dosis queda como **dosis aguda de un evento puntual** (no "por día"), consistente con lo que se anota en `RunAction.cc` — ver `CLAUDE.md`.

---

## Al terminar ambas partes

Avísenme cuando tengan todo esto lleno + los archivos en `data/raw_exports/`, y yo hago:

1. Reformateo de los exports crudos a los 6 CSV que `SpectrumSampler` ya espera (`data/gcr_proton_solarmax.csv`, etc.).
2. La normalización a dosis absoluta en `RunAction.cc`, usando las unidades y la decisión SEP que anotaron arriba.
3. El párrafo de Métodos describiendo exactamente qué modelo (ISO-15390 y ESP-PSYCHIC, ambos vía SPENVIS), qué fecha/confianza, y qué unidades se usaron (para que quede citable en el artículo).
