# ActiveShield_Sim

Simulación Geant4 para estudiar blindaje magnético espacial con fantoma
ICRP110 y dosis por órgano. Base: ejemplo oficial `ICRP110_HumanPhantoms`,
conservado en `README_ICRP110_original.md`; datos descargados durante CMake.
Esta es la v2 del proyecto (ver [README raíz](../../README.md)).

## Estado de revisión (2026-10-01)

La especificación vigente está en [plan_piloto.md](../../docs/bitacora/plan_piloto.md)
y [plan_barrido.md](../../docs/bitacora/plan_barrido.md). Las dosis
históricas radiales y los pilotos Fases 7–10 de la v1 no acreditan la nueva
producción con ley coseno.

Correcciones de esta revisión local:

- `run_organ_sweep.py` rechaza resume con distinto modo angular, eventos o
  grilla y filtros sin coincidencias. Usar salidas separadas para distintas
  configuraciones; `--no-resume` reemplaza los CSV existentes.
- El agregador rechaza fases distintas dentro de GCR o de SEP, números de
  eventos inconsistentes dentro de una corrida, valores no finitos y
  energías incompatibles con su grilla. Procesar min/max en entradas y
  directorios separados; GCR/min junto a SEP/max sigue admitido.
- La vista por bin deja SE/df/IC vacíos si el modelo tiene bins ausentes o
  R=1; los indicadores de datos faltantes acompañan a la suma parcial.
- **Scorer por evento (2026-10-01).** Se activa con `run_organ_sweep.py
  --event-stats [--checkpoints 2500,5000] [--per-event]`. Cada corrida
  escribe en `resultados_eventstats.csv` su dosis por primario, su error
  estándar y su VOV por órgano y categoría. Archiva
  `organ_run_*.eventstats.tsv` junto al `.out`. El SE de una categoría se
  usa solo si cumple el autodiagnóstico: VOV < 0.1 y suficientes eventos
  con depósito, según
  [metodo_autodiagnostico_incertidumbre.md](../../docs/bitacora/metodo_autodiagnostico_incertidumbre.md).
  Requiere el binario actual. No es el default, porque los workers del
  coordinator todavía corren el anterior.
- Radio explícito de agregación: debe ser finito y positivo y coincidir con
  la simulación. Los espectros deben tener energía positiva creciente y
  flujos finitos no negativos.

Estas comprobaciones no sustituyen Q(L), la procedencia completa ni los
pilotos P0–P6. Coordinator y nueva imagen Docker pendientes
para una etapa posterior; esta revisión no los despliega ni construye.

## Geometría y campo vigentes

- Nave: cilindro cerrado de eje Z, casco `G4_Al` de 1.5 cm con tapas del
  mismo espesor, aire interior, exterior en vacío (`G4_Galactic`). En
  producción, radio 4.5 m (CREW HaT, diámetro de Starship) y semilongitud
  5 m (supuesto propio: no hay fuente para CREW HaT).
- Bobinas: CREW HaT, 8 bobinas Halbach elípticas, conductor CORC
  homogeneizado (winding pack 0.67 m; **nunca** la cinta de 12 mm en el
  arreglo completo). Se importan como GDML con su masa y material
  (`/spacecraft/coilGeometry`), fuera de `ShipInterior`, bajo
  `MagnetEnvelope`.
- Campo: mapa Elmer FEM a escala real
  (`field/production/crewhat_elmer_fullscale.map`), global, con
  interpolación trilineal. El mapa Biot-Savart
  (`crewhat_niac_max.map`) se conserva solo para comparar.
- Fantoma ICRP110 masculino o femenino, desplazable en Z
  (`phantomPositionCm`) y en XY (`phantomOffsetX|Y`).
- Blindaje pasivo (`addPassiveLayerCm`) conservado, desactivado por defecto.

Justificación, fuentes y limitaciones en
[decisiones del modelo](docs/modelo_realista.md); procedencia de los
espectros en [checklist_espectros_reales.md](docs/checklist_espectros_reales.md).
Las reglas compartidas viven en [AGENTS.md](../../AGENTS.md).

## Jerarquía geométrica

```text
World (vacío)
└── MagnetEnvelope (vacío)
    ├── ShipHull (Al, sólido exterior menos cavidad)
    ├── ShipInterior (aire)
    │   └── phantomContainer → réplicas/vóxeles ICRP110
    └── bobinas / crióstatos / soportes (pendientes)
```

`MagnetEnvelope` deja 0.5 m respecto a cada cara del mundo. No constituye una
frontera magnética: el campo se registra globalmente en `ConstructSDandField`
y se evalúa con coordenadas del mundo, independientemente del material.

## Compilar y verificar

```bash
cd geant4/ActiveShield_Sim
cmake -S . -B build -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
cmake --build build -j2
ctest --test-dir build --output-on-failure
cd build
./ICRP110phantoms male.in
```

`male.in` y `female.in` mantienen el scorer original por órgano, sin
modificar. `primary.mac` (2026-09-10) ya **no** usa `/gps/...` —
`ICRP110PhantomPrimaryGeneratorAction` dejó de envolver un
`G4GeneralParticleSource` y ahora muestrea espectros reales de OLTARIS;
ver la sección "Primarios, barrido y dosis por órgano" para los comandos (`/gun/species`, `/gun/phase`). Por defecto
`primary.mac` corre `GCR_H` en fase mínima. Son pruebas de funcionamiento;
sus 1000 eventos no fijan el presupuesto estadístico de producción ni
representan 1000 corridas independientes.

### Visualizar una geometría/campo importado (`--vis`, 2026-09-09)

`./ICRP110phantoms` sin argumentos abre ventana gráfica pero ejecuta
siempre `vis.mac` (hardcodeado), que nunca llama a `/spacecraft/...` — no
sirve para ver una bobina importada. `./ICRP110phantoms macro.mac` sí
puede llamar a `/spacecraft/...`, pero corre en modo batch sin ventana:
`/vis/open` sin un driver explícito solo funciona dentro de una sesión
`G4UIExecutive` ya creada, que el modo batch nunca instancia. Para ver una
geometría/campo importado gráficamente, usar el modo nuevo:

```bash
./ICRP110phantoms --vis mi_macro.mac
```

Esto abre la sesión interactiva (como sin argumentos) pero ejecuta
`mi_macro.mac` en vez de `vis.mac` — la macro debe incluir sus propios
comandos `/spacecraft/...` (PreInit, antes de `/run/initialize`) seguidos
de sus propios comandos `/vis/...`. Ver
`tests/demo_particle_tracks.mac` como ejemplo.

## Configuración antes de /run/initialize

```text
/spacecraft/hullThickness 1.5 cm
/spacecraft/shipRadius 2.8 m
/spacecraft/shipHalfLength 5 m
/spacecraft/worldHalfSize 10 m
/spacecraft/coilGeometry /ruta/absoluta/componentes.gdml
/spacecraft/fieldMap /ruta/absoluta/geom14.map
/spacecraft/fieldScale 1
/spacecraft/addPassiveLayerCm G4_Al 1
/spacecraft/phantomPositionCm 0
/spacecraft/phantomOffsetX 0 m
/spacecraft/phantomOffsetY 0 m
/spacecraft/sourceSphereRadius 0 m
```

- `sourceSphereRadius` (2026-10-01): radio de la esfera donde nacen los
  primarios. Con 0 (default) se usa la fórmula histórica: semidiagonal de
  la nave + casco + 20 cm (6.94 m en producción), que corta el arreglo de
  bobinas (radio 5.67–10.34 m). Si el radio no cabe en `MagnetEnvelope`, la
  construcción aborta. El límite de longitud de traza (3·2R) escala solo.
  El agregador usa el radio en el peso `π R² Φ`: pasarle el mismo valor
  con `aggregate_organ_doses.py --source-sphere-radius-m`. Lo
  necesita el piloto P1 de `docs/bitacora/plan_piloto.md`.
- `hullThickness`: positivo y menor de 100 cm, dimensiones exteriores fijas.
- `shipRadius`/`shipHalfLength`: radio y semilongitud del cilindro de la
  nave (por defecto 2,8m/5m, tamaño de Geom14/ARSSEM). CREW HaT usa
  4,5m de radio (referencia NIAC, diámetro de Starship); la semilongitud
  no tiene fuente para CREW HaT, se mantiene el valor por defecto como
  supuesto propio explícito (ver `docs/modelo_realista.md`).
- `coilGeometry`: omitir para no importar piezas. Acepta el contrato GDML
  de `field/mesh_to_gdml.py` (componentes teselados sin hijos). CMake requiere
  GDML. Importa materiales y geometría, independientemente del campo; valida
  límites de envolvente/mapa y solapamientos antes del transporte.
- `worldHalfSize`: mínimo solicitado, mayor de 6 m; para mapas se amplía
  por eje hasta `max(mínimo, abs(límites del mapa) + 1 m)`.
- `fieldMap`: omitir para no cargar campo. Un mapa inválido causa error fatal;
  debe extenderse más allá de todo el hábitat en X, Y y Z.
- `fieldScale 0`: mismo mapa y dominio, campo apagado; útil como control.
  Un factor distinto de 1 solo representa un cambio de corriente proporcional
  si el modelo electromagnético es lineal y la geometría permanece fija.
- `addPassiveLayerCm <G4_Al|G4_POLYETHYLENE> <espesor_cm>`: agrega una capa
  pasiva fuera del casco, de adentro hacia afuera en el orden en que se
  llama. Legado del blindaje pasivo comparativo, desactivado si no se usa.
- `phantomOffsetX`/`phantomOffsetY` (2026-09-10): desplaza el fantoma
  dentro de `ShipInterior`, en el plano perpendicular al eje de la nave.
  Por defecto 0 (fantoma centrado en el eje, comportamiento histórico sin
  cambios). Habilita el barrido de posición, motivado por que el campo
  Halbach de CREW HaT es no uniforme. Un offset que
  saque el fantoma de `ShipInterior` se detecta por el chequeo de
  solapamiento nativo de Geant4, no por una validación propia.
- Los parámetros están restringidos a PreInit: usar un proceso por configuración.
- `phantomPositionCm`: desplazamiento del fantoma a lo largo del **eje Z**
  (eje largo del cilindro `ShipInterior`, un `G4Tubs` sin rotación) — no es
  el mismo eje que `phantomOffsetX`.
  No negativo (`positionCm>=0`), acotado en la práctica por `shipHalfLength`
  menos la mitad del fantoma; un valor demasiado grande produce solapamiento
  geométrico (`G4PVPlacement` con `checkOverlaps=true` lo reporta en el log).

## Contrato del mapa

Archivo de texto `.map`, espacios como separador, comentarios `#` admitidos:

```text
# nx ny nz (enteros >=2)
2 2 2
# xmin ymin zmin [m], coordenadas globales
-8 -8 -8
# dx dy dz [m], positivos
16 16 16
# Bx By Bz [T], x cambia mas rapido, luego y, luego z
0 0 0
0 0 0
0 0 0
0 0 0
0 0 0
0 0 0
0 0 0
0 0 0
```

Este ejemplo **solo prueba el formato**, no representa el campo del imán.
Python debe remuestrear el resultado FEM sobre la grilla y exportar con
orden `for z: for y: for x:` y suficiente precisión (`.17g`). Los tres
componentes son vectores en el mismo sistema de ejes que la geometría.
No exportar únicamente |B|. No se admite un `.msh` o `.vtu` directamente.

El lector valida dimensiones, espaciado, datos finitos y cantidad de valores.
Interpola dentro del dominio, incluidas sus caras, y devuelve **cero fuera**.
Imprime los límites, la escala y el máximo |B| en sus caras: el corte exterior
es una aproximación que exige convergencia, no una afirmación de campo nulo.
`G4CachedMagneticField` no lee ni interpola mapas; no se utiliza aquí.

La prueba CTest verifica un campo afín con divergencia nula sobre grilla no
cúbica, unidades, interpolación interior, caras, exterior, escala y entradas
inválidas. No sustituye validar el mapa físico contra Elmer/Biot-Savart.

## Primarios, barrido y dosis por órgano

### Fuente de primarios

`ICRP110PhantomPrimaryGeneratorAction` muestrea los seis espectros de
OLTARIS (`data/sources/oltaris/`, copiados a `build/data/` por CMake) con
`SpectrumSampler`. Comandos (Idle, después de `/run/initialize`):

```text
/gun/species GCR_H|GCR_He|SEP_p
/gun/phase max|min
/gun/fixedEnergyMeV <valor>   # opcional -- MeV/amu (GCR_H|GCR_He) o MeV (SEP_p)
/gun/angularDistribution radial|cosine   # default radial (histórico)
```

- `fixedEnergyMeV` fuerza una energía monoenergética: el barrido usa
  **bins de energía + reponderación**, no muestreo continuo.
- `angularDistribution cosine` hace entrar a los primarios con ley coseno,
  la única distribución compatible con el peso `π R² Φ` del agregador.
  `radial` (todos apuntan al origen) se conserva solo para reproducir
  corridas v1; el barrido v2 usa `cosine`. Ver
  [modelo_realista.md](docs/modelo_realista.md), "Hallazgo crítico
  (2026-09-30)", y la verificación de la normalización en
  [`tests/verificacion_fuente/`](tests/verificacion_fuente/README.md).

Una corrida tiene una sola especie y un solo bin de energía: el scoring
(`G4ScoringManager`/`ICRP110UserScoreWriter`) no distingue nada dentro de
una corrida, y la combinación de bins con sus pesos se hace en Python.

### Lanzador: `scripts/run_organ_sweep.py`

Corre `especie × bin × posición(offsetX) × repetición`, una corrida por
proceso, y archiva cada `ICRP110.out` (el scorer siempre escribe ese nombre
fijo) antes de lanzar la siguiente. Escribe `resultados_organo_sweep.csv` y
un manifiesto con semillas y configuración; resume por defecto
(`--no-resume` para rehacer). Flags principales:

- `--field-map`/`--coil-geometry`: por defecto apuntan a `field/production/`;
  `--no-coil-geometry` omite la masa de las bobinas.
- `--angular-distribution radial|cosine` (default `radial`, histórico; usar
  `cosine`).
- `--n-bins` (default 8), `--n-events`, `--repeats`, `--threads` (todos los
  núcleos; el resultado es idéntico bit a bit entre 1, 4 y 14 hilos).
- Filtros para repartir: `--only-species`, `--only-phase`, `--only-bins`,
  `--skip-bins`, `--only-positions`, `--limit`.
- `--event-stats [--checkpoints ...] [--per-event]`: scorer por evento (ver
  "Estado de revisión" arriba).

Los valores por defecto (8 bins, posiciones 0–4 m, 10000 eventos) son los
de la v1. Los de la v2 los fijan los pilotos P1–P4 de
[plan_piloto.md](../../docs/bitacora/plan_piloto.md).

### `scripts/energy_bins.py`

Bins log-espaciados por especie y fase dentro del rango que cubre >99.9%
del flujo o fluencia de cada espectro, con energía representativa en la
media geométrica de los bordes y peso por integral trapezoidal en el
sub-rango.

### `scripts/aggregate_organ_doses.py`

Combina las corridas con el peso `W[s,bin] = π R² × flujo integrado del
bin` (`--source-sphere-radius-m` debe coincidir con la simulación) y aplica
`w_R` de ICRP 103 por especie primaria (protón 2, alfa 20; un secundario
hereda el `w_R` del primario). Produce:

- `resultados_organo_agregados.csv`: dosis absorbida y equivalente por
  órgano y posición;
- `resultados_riesgo_estocastico*.csv`: las 6 categorías con
  `w_T = 0.12` de ICRP 103 (colon, pulmón, estómago, mama, médula ósea roja
  y tejidos restantes), ponderadas por masa.

GCR (Gy/día) y SEP (Gy/evento) tienen distinta semántica temporal y no se
suman. La médula ósea roja cruza `AM_organs.dat`, `AM_spongiosa.dat` y
`OrganMasses.dat` (19 sitios esqueléticos por su fracción RBM; masa
1.170 kg, igual a la de referencia ICRP). Las agrupaciones excluyen los
"contents" (heces, contenido gástrico, sangre en cámaras cardíacas): es una
decisión de modelado propia, no una convención ICRP verificada. Para P0, la
comparación con ICRP 116 usa los órganos individuales de ICRP (ver
[`tests/p0_normalizacion/`](tests/p0_normalizacion/README.md)).

**Limitación:** con el fantoma masculino, la dosis en mama es una
referencia dosimétrica, no equivalente al riesgo epidemiológico en mujeres.

### Physics list

`Shielding`, vía `G4PhysListFactory` en `ICRP110phantoms.cc`.
