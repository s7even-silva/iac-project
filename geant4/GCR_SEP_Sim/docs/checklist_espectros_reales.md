# Checklist: extraer espectros reales (OLTARIS: BON2020 + Historical SPE)

Guía para no tener que volver a correr las herramientas por falta de un dato. Guarda todo en `geant4/GCR_SEP_Sim/data/sources/oltaris/raw_exports/` (crear la carpeta si no existe) antes de reformatear a CSV.

**Cambio de plan (2026-09-08):** se aprobó el acceso a OLTARIS. Reemplaza el plan intermedio con SPENVIS (ISO-15390 para GCR, ESP-PSYCHIC para SEP) — `data/sources/spenvis/` se conserva como plan B, no se borra. Modelos activos ahora: **Badhwar-O'Neill 2020** para GCR, **evento histórico** para SEP (no el modelo probabilístico ESP-PSYCHIC). Ver la carpeta [`data/sources/oltaris/README.md`](../data/sources/oltaris/README.md) para el detalle técnico de cómo activar esta fuente una vez llena.

**Por qué importa anotar todo esto:** vamos a necesitar los mismos datos más adelante para (a) calcular los pesos por bin de energía (`W[s,i]`, ver `ActiveShield_Sim/docs/modelo_realista.md`), (b) la normalización a dosis absoluta en `RunAction.cc`, y (c) la sección de Métodos del artículo — si falta una unidad o un supuesto, hay que volver a entrar a la herramienta.

Herramienta: https://oltaris.larc.nasa.gov/

**Nota sobre el formato ahora que se decidió simular por bins (no muestreo continuo):** pide la tabla **lo más granular posible** (muchos puntos de energía), no una curva suavizada — se va a integrar numéricamente sobre los bordes de bin que se definan después, y cuantos más puntos tenga la tabla original, más precisa sale esa integración.

---

## Parte 1 — GCR (Free Space, Badhwar-O'Neill 2020)

- [ ] Ambiente: **Free Space**, modelo GCR = **Badhwar-O'Neill 2020**.
- [ ] Periodo histórico de **mínimo solar** seleccionado — anotar fechas exactas: ______________
- [ ] Periodo histórico de **máximo solar** seleccionado — anotar fechas exactas: ______________
- [ ] Especies exportadas: **H (Z=1)** y **He (Z=2)** por separado (no la suma total).
- [ ] Cantidad exportada: ¿flujo diferencial (dJ/dE) o integral (J>E)? → anotar cuál: ______________
- [ ] **Unidades exactas** tal como las muestra OLTARIS (ej. `partículas / (cm² · s · sr · MeV/nucleón)`): ______________
- [ ] Rango de energía exportado (MeV/nucleón, min–max): ______________
- [ ] Archivos guardados en `data/sources/oltaris/raw_exports/`, ej.:
  - `oltaris_BON2020_H_solarmin.csv` / `oltaris_BON2020_H_solarmax.csv`
  - `oltaris_BON2020_He_solarmin.csv` / `oltaris_BON2020_He_solarmax.csv`
- [ ] Captura de pantalla de la configuración (periodo, especies, rango de energía) guardada junto a los exports — sin esto no se puede reproducir la corrida si falta un dato.

---

## Parte 2 — SEP (Environment Definition: SPE, Free Space 1AU)

**A diferencia de GCR, aquí no hay un selector "max/min" simétrico** — OLTARIS ofrece un catálogo de eventos históricos puntuales bajo "Historical SPE", cada uno seleccionable con checkbox + factor de multiplicación (dejar en 1.0). Máximo y mínimo son **dos eventos distintos**, no el mismo evento con distinta fase:

| Fase | Evento elegido | Por qué |
|---|---|---|
| **Máximo** | **Octubre 1989** (checkbox "Oct 1989") | Peor caso estándar en el rango 5-100 MeV (el mismo que usa CREME-96 como referencia); ~4-19×10⁹ p/cm² >30 MeV según la fuente. |
| **Mínimo** | **Febrero 1956, ajuste LaRC** (checkbox "Feb 1956 (LaRC)") | El más pequeño de los eventos catalogados en OLTARIS con dato comparable, ~1×10⁹ p/cm² >30 MeV — 5 a 20 veces menor que los demás. Se descartó usar "sin evento" para el mínimo: da dosis ≈0 y anula la comparación de efectividad del campo magnético para ese cuarto de la matriz de escenarios (campo×posición no tendría nada que atenuar). |

Notas sobre la elección:
- Marcar **un solo evento por corrida** (no combinar varios checkboxes) — más simple de citar en Métodos.
- Hay dos ajustes distintos para Feb 1956 (Webber y LaRC) — se eligió **LaRC**, anotarlo así en Métodos.
- Carrington 1859 (las dos opciones "hard fit"/"soft fit") es el evento más grande de la lista, pero es una reconstrucción por proxies (no medido directamente) — no se usa aquí, se dejó como referencia de extremo superior si en algún momento se quiere una tercera comparación.

### ⚠️ Paso crítico, fácil de pasar por alto

En la pantalla **"Environment Definition: SPE, Free Space 1AU"**, el campo **"Save external differential flux for space environment?" está en "No" por defecto — cambiarlo a "Sí".** Ese toggle es lo que exporta el **espectro incidente crudo** que necesitamos.

**No usar** el checkbox "Differential Flux/Fluence" de la siguiente pantalla ("Geometry" / "Response Functions") como fuente del CSV — ese es el flujo **después** de atravesar el blindaje slab/esfera que se configure ahí mismo en OLTARIS. Usarlo aplicaría blindaje dos veces (una vez en OLTARIS, otra en nuestro propio Geant4). En esa pantalla no hace falta marcar nada en particular — cualquier geometría mínima (ej. Slab) alcanza para que el sistema deje correr y exportar.

- [ ] Corrida **"SEP máximo"** (Oct 1989): "Save external differential flux" = **Sí**. Exportado.
- [ ] Corrida **"SEP mínimo"** (Feb 1956, LaRC): "Save external differential flux" = **Sí**. Exportado.
- [ ] Especie exportada: confirmar que es **protón** (debería ser lo único disponible para SEP).
- [ ] **Unidades exactas** del export (ej. `protones/cm²` diferencial vs. energía): ______________
- [ ] Rango de energía exportado (MeV, min–max): ______________
- [ ] Archivos guardados en `data/sources/oltaris/raw_exports/`, ej.:
  - `oltaris_SPE_oct1989_proton.csv`
  - `oltaris_SPE_feb1956_LaRC_proton.csv`
- [ ] Captura de pantalla de ambas configuraciones (evento marcado, factor 1.0, toggle en "Sí") guardada junto a los exports.

Con un evento histórico puntual, la interpretación de dosis sigue siendo **dosis aguda de un evento**, sin factor de tiempo — consistente con la fórmula ya anotada en `AGENTS.md`: `dosis_Gy_del_evento = dosis_sim × (fluencia_evento × área_fuente) / N`.

---

## Al terminar ambas partes

Avísenme cuando tengan todo esto lleno + los archivos en `data/sources/oltaris/raw_exports/`, y yo hago:

1. Reformateo de los exports crudos a los 6 CSV que van en `data/sources/oltaris/` (`gcr_proton_solarmax.csv`, etc. — mismo contrato de `SpectrumSampler` que ya usa `spenvis/`).
2. El cálculo de los pesos por bin (`W[s,i]`) a partir de estos espectros, una vez que se fijen los bordes de bin (puntos 6-7 de la lista de pendientes).
3. La normalización a dosis absoluta en `RunAction.cc`/el pipeline de `ActiveShield_Sim`, usando las unidades que anotaron arriba.
4. El párrafo de Métodos describiendo exactamente qué modelo (BON2020, evento Oct 1989, evento Feb 1956 LaRC), qué periodos/eventos, y qué unidades se usaron.
