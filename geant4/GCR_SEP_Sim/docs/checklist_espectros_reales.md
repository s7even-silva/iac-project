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

- [ ] Cuenta creada / acceso confirmado.
- [ ] Modelo corrido: **ESP-PSYCHIC**, protones.
- [ ] **Duración de misión / periodo de exposición usado**: ______________ (ESP-PSYCHIC da fluencia acumulada para una duración elegida por el usuario — esto define qué significa "SEP max/min" en nuestro estudio, ver nota abajo)
- [ ] **Nivel de confianza elegido** (ej. 50%, 95%, 99% — el modelo es probabilístico, el resultado cambia mucho según esto): ______________
- [ ] Corrida para **"solar mínimo"**: parámetros usados: ______________
- [ ] Corrida para **"solar máximo"**: parámetros usados: ______________
- [ ] **Unidades exactas** del export (ej. `protones/cm²` acumulado, o `protones/(cm²·MeV)`): ______________
- [ ] Rango de energía exportado (MeV, min–max): ______________
- [ ] Archivo(s) guardado(s) en `data/raw_exports/`, ej.:
  - `spenvis_ESP-PSYCHIC_proton_solarmin.csv`
  - `spenvis_ESP-PSYCHIC_proton_solarmax.csv`
- [ ] Captura de pantalla de la configuración del modelo guardada en `data/raw_exports/spenvis_config_screenshot.png`.

### ⚠️ Decisión pendiente que afecta el resultado (anotar la respuesta, no solo el dato)

ESP-PSYCHIC da **fluencia acumulada de un evento/periodo**, no una tasa continua como GCR. Hay que decidir y anotar cuál interpretación estamos usando para "dosis SEP":

- [ ] **Opción A**: dosis de un evento SEP puntual (fluencia total de un evento típico/peor caso) → dosis aguda, no "por día".
- [ ] **Opción B**: fluencia anualizada (fluencia acumulada de la duración de misión elegida, dividida entre esa duración) → dosis promedio por día/año, comparable directamente con GCR.

Anotar cuál se usó: ______________ (esto va a determinar la fórmula de normalización en `RunAction.cc`, así que avísenme cuál eligieron antes de que implemente esa parte).

---

## Al terminar ambas partes

Avísenme cuando tengan todo esto lleno + los archivos en `data/raw_exports/`, y yo hago:

1. Reformateo de los exports crudos a los 6 CSV que `SpectrumSampler` ya espera (`data/gcr_proton_solarmax.csv`, etc.).
2. La normalización a dosis absoluta en `RunAction.cc`, usando las unidades y la decisión SEP que anotaron arriba.
3. El párrafo de Métodos describiendo exactamente qué modelo, qué periodo/confianza, y qué unidades se usaron (para que quede citable en el artículo).
