# IAC 2026

Las instrucciones y decisiones del proyecto se mantienen en [AGENTS.md](AGENTS.md).
`CLAUDE.md` importa ese archivo mediante `@AGENTS.md` para que Claude Code
cargue las mismas instrucciones sin duplicar su contenido.

## Estado de producción

`geant4/ActiveShield_Sim` es el proyecto del modelo realista: exterior en vacío,
casco de referencia Al de 1.5 cm, envolvente para bobinas externas y lector de
campo global. Existe un [piloto Double Helix y campo de referencia](field/README.md);
el ensamblaje Geom14 y el mapa físico validado aún faltan. **El equipo ya decidió
simular por bins de energía y reponderar**, no usar el barrido continuo del
piloto como producción. Véanse [estado e interfaces](geant4/ActiveShield_Sim/README.md)
y [decisiones y justificación](geant4/ActiveShield_Sim/docs/modelo_realista.md).

La generación de mallas y conversión de componentes con materiales a GDML
ya dispone de un entorno Python aislado y una prueba de importación en Geant4.
Desde la raíz: `python3 field/bootstrap.py` (Python 3.13, validado con 3.13.5).
El entorno se crea en `field/.venv`, excluido de Git. Procedimiento completo,
dependencias fijadas y ejemplos en [field/README.md](field/README.md).
La conversión está preparada; el devanado real y el cálculo FEM siguen pendientes.

El barrido de 140 combinaciones y las instrucciones de reparto que siguen
corresponden únicamente a `GCR_SEP_Sim`, conservado como piloto de referencia.

## Entorno de simulación

    conda env create -f environment.yml
    conda activate geant4_env

Compilación (fuera de fuente, con el toolchain de conda):

    rm -rf build && mkdir build && cd build
    cmake -DCMAKE_CXX_COMPILER=$CXX ..
    make -j$(nproc)

### Versiones

| Componente | Versión |
|---|---|
| GEANT4 | 11.4.2 (conda-forge) |
| CMake | 4.4.1 |
| Compilador | gcc/gxx_linux-64 15.2.0 |

### Datasets de GEANT4

| Dataset | Versión | Relevancia |
|---|---|---|
| G4EMLOW | 8.8 | Procesos EM de baja energía, poder de frenado |
| G4NDL | 4.7.1 | Transporte de neutrones (HP) — crítico con polietileno |
| G4PARTICLEXS | 4.2 | Secciones eficaces hadrónicas |
| G4ABLA | 3.3 | Desexcitación nuclear — fragmentos secundarios |
| G4INCL | 1.3 | Cascada intranuclear |
| PhotonEvaporation | 6.1.2 | |
| RadioactiveDecay | 6.1.2 | |
| G4ENSDFSTATE | 3.0 | |
| G4SAIDDATA | 2.0 | |
| G4PII | 1.3 | |
| RealSurface | 2.2 | |
| G4CHANNELING | 2.0 | |

### Parámetros de simulación

- Physics list: (por definir — `Shielding` / `QGSP_BIC_HP`)
- Stepper de campo: (por definir)
- Cortes de producción: (por definir)
- Semillas: registradas por corrida en `output/`

## División del trabajo del equipo (barrido de simulaciones)

El barrido de `geant4/GCR_SEP_Sim/` tiene 140 combinaciones (GCR/SEP × fase solar max/min × 7 valores de campo × 5 posiciones del astronauta). Para el artículo necesitamos, por cada combinación, **media, desviación estándar e intervalo de confianza 95%** — eso requiere correr cada combinación varias veces (repeticiones con semillas distintas), no una sola vez. Ya se acordó: **5 repeticiones por combinación** (140 × 5 = 700 corridas en total).

Para terminar a tiempo entre los dos, el trabajo se reparte así:

- **Persona A** corre todas las combinaciones de **GCR** (max + min × 7 campos × 5 posiciones = 70 combinaciones × 5 repeticiones = 350 corridas).
- **Persona B** corre todas las combinaciones de **SEP** (70 combinaciones × 5 repeticiones = 350 corridas).

Se reparte por tipo de evento porque GCR y SEP son ejes físicamente independientes (no hay interacción entre ellos), así que no hay riesgo de inconsistencia al juntar los resultados de cada quien al final — simplemente se concatenan.

### 0. Antes de repartir: verificar que están sincronizados

Ambos deben partir exactamente del mismo código:

    git pull
    git log -1 --oneline   # confirmar que las dos personas ven el mismo commit

Y compilar con el mismo comando (ver nota en `AGENTS.md` sobre el workaround de compilador — `$CXX` no sirve en `geant4_env`, hay que usar `g++` + `CMAKE_PREFIX_PATH`).

Medido en una laptop de gama baja: una corrida de 10000 eventos tarda entre **~2 y ~10 segundos** según la combinación (campo/posición). Con eso, 350 corridas por persona toman entre **~15 y ~60 minutos** — sobra tiempo dentro de una ventana de 4 días incluso con poder de cómputo bajo, así que **no hace falta bajar `--n-events`**. Si en su hardware resulta mucho más lento, midan con un piloto chico antes de lanzar todo:

    cd geant4/GCR_SEP_Sim/build
    python3 ../scripts/run_sweep.py --only-model GCR --n-events 10000 --limit 3

### Si el barrido se corta a la mitad (Ctrl+C, corte de luz, se cierra la sesión SSH sin `tmux`/`screen`)

No hace falta empezar de cero. El binario `gcrsim` va agregando (append) una fila a `resultados_dosis_sweep.csv` por cada corrida que termina, y `run_sweep.py` hace lo mismo con `sweep_manifest.csv` — ninguno de los dos se sobrescribe de golpe al final, así que lo ya corrido antes del corte queda guardado. **Resume está activado por defecto:** basta con relanzar exactamente el mismo comando que se cortó:

    python3 ../scripts/run_sweep.py --only-model GCR --repeats 5 --n-events 10000

El script lee `sweep_manifest.csv` y salta automáticamente toda combinación `(índice, repetición)` que ya haya terminado con éxito (`exit_code 0`); las que fallaron se vuelven a intentar. Si en cambio se quiere rehacer el barrido desde cero a propósito (por ejemplo, tras cambiar algún parámetro que invalida las corridas previas), agregar `--no-resume` — de lo contrario esas corridas viejas quedarían duplicadas en el CSV de resultados.

Si van a dejar el barrido corriendo desatendido en una máquina remota (por ejemplo las de la universidad por SSH), lanzarlo dentro de `tmux` o `screen` para que sobreviva un corte de la conexión:

    tmux new -s sweep
    python3 ../scripts/run_sweep.py --only-model GCR --repeats 5 --n-events 10000
    # Ctrl+B, D para desconectar sin matar el proceso; tmux attach -t sweep para volver a verlo

### 0.5. Fechas de referencia para la fase solar (GCR y SEP)

`/gun/phase max|min` representa la **fase real del ciclo solar**, no "el peor caso de esa especie" — y GCR y SEP reaccionan al revés uno del otro ante esa fase:

- **GCR**: el flujo es **más alto en mínimo solar** (menos viento solar blindeando la heliosfera) y más bajo en máximo solar.
- **SEP**: los eventos grandes son **más frecuentes/severos en máximo solar**, casi no ocurren en mínimo.

**GCR y SEP usan criterios de selección distintos — no hace falta (ni tiene sentido) que compartan fecha de calendario:**

| Fase | GCR: condición del ciclo solar | SEP: severidad del evento histórico |
|---|---|---|
| `min` | Mínimo solar real, dic 2019 – ene 2020 (oficial NASA/NOAA, ciclo 24→25) | **Febrero 1956, ajuste LaRC** — el más pequeño de los eventos catalogados en OLTARIS con dato comparable |
| `max` | Máximo solar real, ventana ene 2024 – jul 2025 (ciclo 25) | **Octubre 1989** — peor caso estándar en el rango 5-100 MeV |

Para GCR importa **la fecha real** (se pregunta "¿cómo es el flujo típico en esa fase del ciclo solar?", y las fechas 2019-2020/2024 son el mínimo/máximo real más reciente, más representativo que un ciclo de hace décadas). Para SEP importa **la magnitud del evento**, no cuándo ocurrió — por eso los eventos elegidos caen en años completamente distintos (1989, 1956) sin relación con las fechas de GCR.

Con esto, el resultado esperado es que **la dosis de GCR salga mayor en `min` que en `max`, y la dosis de SEP salga mayor en `max` que en `min`** — es física real del ciclo solar/severidad de evento, no un error si se da así; coméntenlo en la Discusión del artículo.

Aplicación (**ambos modelos vía OLTARIS** desde 2026-09-08, al aprobarse el acceso — reemplaza el plan intermedio con SPENVIS, que queda como plan B):
- **Badhwar-O'Neill 2020 (GCR)**: usar "Defined by: **Date**", no "Historical Solar Min/Max" — esa lista de años fijos solo llega hasta 2010, no cubre el ciclo solar actual. "Date" sí acepta las fechas 2019-2020/2024 sin problema.
- **Historical SPE (SEP)**: catálogo de eventos puntuales con checkbox + factor de multiplicación (dejar en 1.0) — no un modelo probabilístico como ESP-PSYCHIC. Paso crítico: el toggle "Save external differential flux for space environment?" debe estar en "Sí" (ver [`docs/checklist_espectros_reales.md`](geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md) para el detalle completo y por qué se descartó usar "sin evento" para el mínimo).

### 0.6. Cambiar de fuente de espectros (OLTARIS ↔ SPENVIS, u otra)

El cambio de SPENVIS a OLTARIS del 2026-09-08 ya se hizo (ver arriba); esta
sección documenta el mecanismo general por si hace falta volver a cambiar
de fuente más adelante. El cambio es barato porque el pipeline ya está
separado en capas:

- `SpectrumSampler` (el código C++ que lee el CSV y muestrea energías) es
  **agnóstico a la fuente** — solo espera dos columnas (energía, flujo), sin
  importar si vinieron de SPENVIS, OLTARIS, o cualquier otra herramienta.
  No hay que tocar ni una línea de `SpectrumSampler.cc`/`.hh` ni de
  `PrimaryGeneratorAction.cc` para cambiar de fuente.
- Cada fuente vive en su propia carpeta bajo
  `geant4/GCR_SEP_Sim/data/sources/<fuente>/` (hoy: `oltaris/`, activa desde
  2026-09-08 — cubre GCR y SEP; `spenvis/` conservada como plan B).
  `data/*.csv` (sin la subcarpeta `sources/`) es solo el **destino activo**
  — no se versiona en git (ver `.gitignore`), se regenera con:

      cd geant4/GCR_SEP_Sim
      python3 scripts/select_spectrum_source.py oltaris   # fuente activa hoy
      python3 scripts/select_spectrum_source.py spenvis   # plan B

  (`--only <archivo...>` si se quiere mezclar fuentes por especie/fase —
  usar con cuidado, revisar bien Métodos si se hace).
- Después de cambiar de fuente hay que volver a correr `cmake ..` dentro de
  `build/` (no basta con `make -j`) para que el build recoja los CSV
  nuevos — `CMakeLists.txt` copia `data/` a `build/data/` en la fase de
  configuración de CMake, no en cada compilación.
- Lo único que no es "gratis": la normalización de dosis absoluta en
  `RunAction.cc` (pendiente de implementar, ver `AGENTS.md`) y el párrafo
  de Métodos del artículo, que sí cambian de contenido según la fuente
  (aunque la fórmula conceptual para SEP —fluencia de un evento puntual,
  sin factor de tiempo— es la misma para cualquier evento histórico).

### 1. Correr el barrido asignado

Persona A (GCR):

    python3 ../scripts/run_sweep.py --only-model GCR --repeats 5 --n-events 10000

Persona B (SEP):

    python3 ../scripts/run_sweep.py --only-model SEP --repeats 5 --n-events 10000

Esto genera `build/resultados_dosis_sweep.csv` (una fila por corrida/repetición) y `build/sweep_manifest.csv` (semillas, tiempos, logs de cada corrida — útil para depurar si algo falla).

### 2. Juntar resultados y calcular estadística

Al terminar, cada quien renombra su CSV y lo coloca en `geant4/GCR_SEP_Sim/resultados/` (carpeta versionada en git — son los datos del artículo):

    mkdir -p ../resultados
    cp resultados_dosis_sweep.csv ../resultados/resultados_dosis_sweep_GCR.csv   # (o _SEP.csv, según corresponda)

Con los dos archivos ya en `resultados/`, cualquiera de los dos corre la agregación:

    cd geant4/GCR_SEP_Sim
    python3 scripts/aggregate_results.py resultados/resultados_dosis_sweep_*.csv -o resultados/resultados_agregados.csv

`aggregate_results.py` agrupa por (modelo, fase, campo, posición) y calcula, sin depender de librerías nuevas (solo Python estándar):

| Columna | Significado |
|---|---|
| `n` | repeticiones encontradas para esa combinación (debería ser 5 — el script avisa si no) |
| `dosis_media_Gy` | dosis absorbida promedio |
| `dosis_std_Gy` | desviación estándar muestral |
| `dosis_sem_Gy` | error estándar de la media |
| `ic95_low_Gy` / `ic95_high_Gy` | intervalo de confianza 95% (t de Student) |
| `cv_pct` | coeficiente de variación, % |

`resultados_agregados.csv` es directamente lo que va a la **tabla de resultados del artículo**, y la fuente de datos para la **gráfica** (dosis vs. intensidad de campo, una curva por posición/evento, con barras de error = IC95%) y para lo que se comente en Resultados y Discusión.
