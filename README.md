# IAC 2026

Simulación Geant4 de la dosis por órgano de un astronauta (fantoma ICRP110)
dentro de una nave con blindaje magnético activo CREW HaT, frente a rayos
cósmicos galácticos (GCR) y partículas solares (SEP).

Las instrucciones y decisiones del proyecto se mantienen en [AGENTS.md](AGENTS.md).
`CLAUDE.md` importa ese archivo mediante `@AGENTS.md` para que Claude Code
cargue las mismas instrucciones sin duplicar su contenido.

## Versiones del proyecto

- **v2 (esta rama, `main`, desde 2026-10-01):** barrido corregido después de
  la [auditoría del 2026-09-30](docs/bitacora/auditoria_2026-09-30.md). Antes
  de producir dosis hay que aprobar los pilotos P0–P6 de
  [`plan_piloto.md`](docs/bitacora/plan_piloto.md); la especificación del
  barrido está en [`plan_barrido.md`](docs/bitacora/plan_barrido.md).
- **v1:** piloto esférico `GCR_SEP_Sim`, barrido de 600 corridas con apuntado
  radial y pilotos estadísticos Fases 7–10. Está en el tag `v1.0-piloto`
  (y la rama `v1`); la versión más reciente de cada archivo que salió de
  `main` está en el tag `v1-archivo`. **Sus dosis no son válidas** como
  resultado físico: ver la auditoría.

## Estructura

| Carpeta | Contenido |
|---|---|
| [`geant4/ActiveShield_Sim/`](geant4/ActiveShield_Sim/README.md) | Simulación Geant4 (fantoma ICRP110, nave, bobinas, mapa de campo), lanzador del barrido, agregador y tests. |
| [`field/`](field/README.md) | Pipeline de geometría y campo de las bobinas (Gmsh + Elmer + Python). `field/production/` trae el mapa y el GDML de producción versionados. |
| [`infra/`](infra/README.md) | Coordinator y workers para repartir el barrido entre máquinas. |
| [`docs/bitacora/`](docs/bitacora/) | Planes vigentes, auditoría, método de incertidumbre y referencias del paper. |
| `docker/`, `scripts/` | Imagen del worker e instaladores. |

## Estado

- **Geometría y campo:** CREW HaT, 8 bobinas Halbach elípticas con conductor
  CORC homogeneizado, nave de 4.5 m de radio, campo Elmer FEM a escala real
  (`field/production/crewhat_elmer_fullscale.map`). Biot-Savart se conserva
  solo para comparación; la cifra histórica "Biot-Savart da 36–48% más dosis"
  no se reprodujo (0.93 ± 0.08 a 562 MeV). Ver
  [`modelo_realista.md`](geant4/ActiveShield_Sim/docs/modelo_realista.md).
- **Bloqueante:** regenerar el mapa Elmer con la esfera fuente que fije P1
  (12–16 m). Necesita una máquina con más RAM que la de desarrollo.
- **Physics list:** `Shielding`.
- **Incertidumbre:** scorer por evento con autodiagnóstico VOV (ver
  [`metodo_autodiagnostico_incertidumbre.md`](docs/bitacora/metodo_autodiagnostico_incertidumbre.md)).

## Entorno de simulación

### Instalación automática (recomendada, cualquier distro Linux)

    bash scripts/install.sh

Instala y configura todo lo necesario desde cero: dependencias de sistema
(compilador, `libGLU` que requiere Gmsh en tiempo de ejecución — detecta
apt/dnf/yum/pacman/zypper/apk automáticamente), Miniconda si no está
presente, el entorno `geant4_env` (Geant4 11.4.2 + CMake + gcc/g++ de
conda-forge, vía `environment.yml`), un entorno conda auxiliar
`py313_bootstrap` (solo para tener un intérprete Python 3.13.x disponible
en cualquier distro sin depender de qué versión traiga cada gestor de
paquetes en sus repos), y `field/.venv` (Gmsh + NumPy, aislado de conda —
ver [field/README.md](field/README.md) sobre por qué). Al final compila
`ActiveShield_Sim` y corre los tests de `field/` para confirmar que todo
quedó operativo.

Es idempotente: se puede volver a correr sin romper una instalación ya
hecha (cada paso comprueba si su resultado ya existe). Usar
`bash scripts/install.sh --skip-system` para omitir el paso que pide sudo
(útil si las dependencias de sistema ya están instaladas, o si se corre en
un entorno sin acceso a sudo). Elmer no se instala por defecto: agregar
`--with-elmer` (compila Elmer FEM, ~15–30 min).

**Nodo de cómputo (voluntarios/CI):** si la máquina solo va a **correr**
simulaciones, no a regenerar geometría/campo, usa
`bash scripts/install_compute_node.sh` — Geant4 sin Qt6 (build `noqt`,
misma física, verificado bit a bit idéntico), sin `field/.venv` ni Elmer,
~400MB menos de instalación. `field/production/` ya trae lo necesario.

**Cómputo distribuido:** coordinator FastAPI + workers en Docker. Ver
[`infra/README.md`](infra/README.md) y la sección correspondiente de
`AGENTS.md`.

### Compilación manual

En `geant4_env` la variable `$CXX` está vacía y `cmake` se resuelve al del
sistema, así que hay que pasar el compilador y el prefijo explícitamente:

    conda env create -f environment.yml
    conda activate geant4_env
    cd geant4/ActiveShield_Sim
    cmake -S . -B build -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
    cmake --build build -j$(nproc)
    ctest --test-dir build --output-on-failure

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
| G4NDL | 4.7.1 | Transporte de neutrones (HP) |
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

## Espectros de entrada (OLTARIS)

Seis espectros reales en `geant4/ActiveShield_Sim/data/sources/oltaris/`
(procedencia y exportaciones crudas en esa carpeta y en
[`checklist_espectros_reales.md`](geant4/ActiveShield_Sim/docs/checklist_espectros_reales.md)):

| Fase | GCR (Badhwar-O'Neill 2020, fecha) | SEP (evento histórico) |
|---|---|---|
| `min` | Mínimo solar, 31/12/2019–01/01/2020 | Febrero 1956, ajuste LaRC |
| `max` | 14–15/01/2023 (no el pico del ciclo 25: BON2020 en OLTARIS no acepta fechas posteriores) | Octubre 1989 |

`/gun/phase max|min` representa la fase real del ciclo solar, no "el peor
caso": el flujo GCR es mayor en mínimo solar y los SEP grandes son más
frecuentes en máximo. Los CSV de GCR vienen en partículas/(día·cm²) y los
de SEP en partículas/cm² (fluencia del evento completo), así que las dosis
de GCR son por día y las de SEP por evento; no se suman. La limitación de
fecha de GCR máximo debe quedar explícita en Métodos.
