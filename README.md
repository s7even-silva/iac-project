# IAC 2026

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

Y compilar con el mismo comando (ver nota en `CLAUDE.md` sobre el workaround de compilador — `$CXX` no sirve en `geant4_env`, hay que usar `g++` + `CMAKE_PREFIX_PATH`).

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

Por eso hay que usar la **misma fecha de calendario** en ambas herramientas (OLTARIS para GCR, SPENVIS para SEP) para cada fase, así el parámetro significa lo mismo en los dos casos:

| Fase | Fecha de referencia | Por qué |
|---|---|---|
| `min` | **enero 2020** | El mínimo solar del ciclo 24→25 fue en diciembre 2019 (fecha oficial NASA/NOAA); enero 2020 cae justo después. |
| `max` | **enero 2024** (o cualquier fecha entre 2024 y 2025) | Ventana de máximo del ciclo 25 observada/estimada por NASA/NOAA (aprox. enero 2024 – julio 2025). |

Con esto, el resultado esperado es que **la dosis de GCR salga mayor en `min` que en `max`, y la dosis de SEP salga mayor en `max` que en `min`** — es física real del ciclo solar, no un error si se da así; coméntenlo en la Discusión del artículo.

Aplicación en cada herramienta:
- **OLTARIS (GCR)**: usar la opción de periodo histórico de mínimo/máximo solar, o el rango de fechas manual, centrado en las fechas de la tabla de arriba.
- **SPENVIS ESP-PSYCHIC (SEP)**: la fecha de inicio de misión (o el "offset en el ciclo solar" en modo avanzado) se fija con estas mismas fechas — mantener la misma duración de misión y nivel de confianza entre la corrida `max` y la `min` (ver [`docs/checklist_espectros_reales.md`](geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md)).

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

