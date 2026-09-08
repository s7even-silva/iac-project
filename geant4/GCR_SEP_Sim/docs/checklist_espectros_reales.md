# Checklist: extraer espectros reales (OLTARIS: BON2020 + Historical SPE)

Guía para no tener que volver a correr las herramientas por falta de un dato. Guarda todo en `geant4/GCR_SEP_Sim/data/sources/oltaris/raw_exports/` (crear la carpeta si no existe) antes de reformatear a CSV.

**Cambio de plan (2026-09-08):** se aprobó el acceso a OLTARIS. Reemplaza el plan intermedio con SPENVIS (ISO-15390 para GCR, ESP-PSYCHIC para SEP) — `data/sources/spenvis/` se conserva como plan B, no se borra. Modelos activos ahora: **Badhwar-O'Neill 2020** para GCR, **evento histórico** para SEP (no el modelo probabilístico ESP-PSYCHIC). Ver la carpeta [`data/sources/oltaris/README.md`](../data/sources/oltaris/README.md) para el detalle técnico de cómo activar esta fuente una vez llena.

**Por qué importa anotar todo esto:** vamos a necesitar los mismos datos más adelante para (a) calcular los pesos por bin de energía (`W[s,i]`, ver `ActiveShield_Sim/docs/modelo_realista.md`), (b) la normalización a dosis absoluta en `RunAction.cc`, y (c) la sección de Métodos del artículo — si falta una unidad o un supuesto, hay que volver a entrar a la herramienta.

Herramienta: https://oltaris.larc.nasa.gov/

**Nota sobre el formato ahora que se decidió simular por bins (no muestreo continuo):** pide la tabla **lo más granular posible** (muchos puntos de energía), no una curva suavizada — se va a integrar numéricamente sobre los bordes de bin que se definan después, y cuantos más puntos tenga la tabla original, más precisa sale esa integración.

---

## Parte 1 — GCR (Environment Definition: GCR, Free Space 1AU)

- [ ] GCR Model: **Badhwar-O'Neill 2020**.
- [ ] **Marcar el checkbox "Select Specific Ion"** — sin esto no se puede pedir H y He por separado (default es algún espectro combinado, no lo que necesitamos). Al marcarlo se abre un selector de ion (Z/A): correr una vez para **H** y otra para **He**, en cada fase → 4 corridas en total.
- [ ] Defined by: **Date** (NO "Historical Solar Min/Max" — esa lista de años fijos solo llega hasta 2010 y no incluye el ciclo solar actual/reciente; confirmado que "Date" acepta fechas de 2019-2024 sin problema).
- [ ] Fecha para **mínimo solar**: una fecha entre **diciembre 2019 y enero 2020** (mínimo oficial NASA/NOAA del ciclo 24→25) — anotar la fecha exacta usada: ______________
- [ ] Fecha para **máximo solar**: una fecha de **enero 2024** (o cualquiera dentro de la ventana 2024-2025 del ciclo 25) — anotar la fecha exacta usada: ______________
- [ ] **Importante:** estas fechas se eligen porque son el mínimo/máximo solar real más reciente — **no** tienen que coincidir con las fechas de los eventos SEP (Oct 1989, Feb 1956). GCR y SEP usan criterios de selección distintos: GCR pide "la condición típica de esa fase del ciclo solar" (por eso importa la fecha real), SEP pide "el evento histórico más grande/chico documentado" (por eso importa la magnitud del evento, no cuándo ocurrió ni en qué fase solar de esa época cayó). No hay ninguna relación de calendario que mantener entre los dos.
- [ ] **"Mission duration in days"**: campo nuevo que no estaba anticipado — viene en `0.0` por defecto. No hay certeza de qué representa exactamente (¿espectro instantáneo en esa fecha vs. algo integrado/promediado en la duración?) — **revisar el link "Help" de esa pantalla antes de correr**; si no aclara, probar primero con `0.0` (el default) y solo cambiar a otro valor (ej. `1`) si el resultado no tiene sentido o da error. Anotar qué valor se terminó usando: ______________
- [ ] **"Save external differential flux for space environment?" = Sí** (ya viene así en la interfaz — confirmar que sigue en Sí después de tocar los demás campos).
- [ ] En la pantalla de **Geometry / Response Functions** que sigue: no marcar ninguna "Response Function" (Dose, Dose Equivalent, Effective Dose Equivalent, RIED, LET, etc.) — no las necesitamos (ya se obtiene el espectro crudo con el toggle anterior) y algunas piden campos adicionales (ej. "Age" para RIED) que solo estorban. Cualquier geometría mínima (ej. "Thk Distrib" con "zero sphere", que representa blindaje cero) sirve para dejar correr.
- [ ] Cantidad exportada: ¿flujo diferencial (dJ/dE) o integral (J>E)? → anotar cuál: ______________
- [ ] **Unidades exactas** tal como las muestra OLTARIS (ej. `partículas / (cm² · s · sr · MeV/nucleón)`): ______________
- [ ] Rango de energía exportado (MeV/nucleón, min–max): ______________
- [ ] Archivos guardados en `data/sources/oltaris/raw_exports/`, ej.:
  - `oltaris_BON2020_H_solarmin.csv` / `oltaris_BON2020_H_solarmax.csv`
  - `oltaris_BON2020_He_solarmin.csv` / `oltaris_BON2020_He_solarmax.csv`
- [ ] Captura de pantalla de la configuración completa (modelo, ion, periodo, duración de misión, rango de energía) guardada junto a los exports — sin esto no se puede reproducir la corrida si falta un dato.

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
