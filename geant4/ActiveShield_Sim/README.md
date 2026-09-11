# ActiveShield_Sim

Simulación Geant4 para estudiar blindaje magnético espacial con fantoma
ICRP110 y dosis por órgano. Base: ejemplo oficial `ICRP110_HumanPhantoms`,
conservado en `README_ICRP110_original.md`; datos descargados durante CMake.

## Estado actual y decisiones (2026-09-08)

- Geometría del hábitat: cilindro cerrado, diámetro exterior **5.6 m**, largo
  exterior **10 m**, eje Z. Casco de **G4_Al, 1.5 cm**, tapas planas del mismo
  espesor. Es una referencia radiológica, no un diseño estructural de vuelo.
- Exterior **G4_Galactic** (vacío); aire del hábitat y materiales ICRP110
  conservados. Fantoma masculino o femenino, centrado en X/Y; desplazable a
  lo largo del eje Z de la nave vía `/spacecraft/phantomPositionCm` desde
  2026-09-10 (ver sección "Dosis por órgano y equivalente" más abajo) —
  revierte la decisión previa de "sin barrido de posición" para el análisis
  de riesgo estocástico.
- Casco y cabina son hermanos bajo `MagnetEnvelope`, un volumen en vacío
  que también alojará bobinas y crióstatos externos. No colocar bobinas
  externas como hijas de `ShipInterior`.
- Lector de mapa cartesiano regular con interpolación trilineal y campo
  **global**, también en el exterior. Sin mapa, campo apagado. Mundo mínimo
  de semilado 10 m, ampliado automáticamente si el mapa lo requiere.
- **Todavía no hay devanado real ni mapa físico de Elmer.** Ya existe una
  conversión de mallas tetraédricas de Gmsh a componentes GDML con materiales,
  y su carga mediante `/spacecraft/coilGeometry`. Ejemplo Cu/Al y entorno
  Python reproducible en [field/README.md](../../field/README.md).
- Piloto DH paramétrico con retornos cerrados y mapa Biot–Savart de referencia:
  secuencia en esa misma guía. Alcance, materiales pendientes de Geom14 y
  preparación reproducible del ensayo 2A/4A/8A en
  [verificación de dominios](../../field/DOMAINS.md). Es un ensayo de desarrollo,
  no una configuración radiológica de producción.
- El equipo decidió **bins de energía + reponderación**, sustituyendo el
  muestreo continuo para la producción de este proyecto. GPS ya permite
  energías monoenergéticas; faltan el orquestador por bins, su estadística
  por órgano y los pesos físicos. No se han fijado aún bins ni eventos/bin.
- Pipeline externo elegido: **Gmsh + Elmer + Python**. Geom14 de ARSSEM es
  la recomendación de referencia; no se ha implementado ni fijado su
  devanado. El usuario indica que el plan previo era de 12 bobinas.

La justificación, fuentes, limitaciones, normalización por bins y comparación
con blindaje pasivo están en [decisiones del modelo](docs/modelo_realista.md).
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
`G4GeneralParticleSource` y ahora muestrea espectros reales de OLTARIS,
igual que `GCR_SEP_Sim`; ver la sección "Dosis por órgano y equivalente"
para los comandos nuevos (`/gun/species`, `/gun/phase`). Por defecto
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
`tests/dh_pilot_vis.mac` como ejemplo.

## Configuración antes de /run/initialize

```text
/spacecraft/hullThickness 1.5 cm
/spacecraft/worldHalfSize 10 m
/spacecraft/coilGeometry /ruta/absoluta/componentes.gdml
/spacecraft/fieldMap /ruta/absoluta/geom14.map
/spacecraft/fieldScale 1
/spacecraft/phantomPositionCm 0
```

- `hullThickness`: positivo y menor de 100 cm, dimensiones exteriores fijas.
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
- Los parámetros están restringidos a PreInit: usar un proceso por configuración.
- `phantomPositionCm`: desplazamiento del fantoma a lo largo del **eje Z**
  (eje largo del cilindro `ShipInterior`, un `G4Tubs` sin rotación) — no es
  el mismo eje que `/detector/astronautX` de `GCR_SEP_Sim` (ahí
  `ShipInterior` es una esfera, así que "X" era una convención arbitraria).
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

## Dosis por órgano y equivalente (2026-09-10)

Objetivo: dosis equivalente (Sv) en los órganos de mayor riesgo estocástico
de cáncer (ICRP 103 Tabla A.1, los `w_T=0.12` más altos: médula ósea roja,
colon, pulmón, estómago, mama), en función de **dónde está el fantoma
dentro de la nave**, en el escenario de **blindaje magnético máximo** (10 T,
el tope del barrido de `GCR_SEP_Sim`) y **el evento más peligroso de cada
especie** (GCR en mínimo solar — mayor flujo GCR — y SEP en Oct 1989, el
peor caso ya documentado). Ver `AGENTS.md` para el porqué de este alcance
reducido (no es un barrido de campo/fase completo).

**`ICRP110PhantomPrimaryGeneratorAction` reescrito:** ya no envuelve un
`G4GeneralParticleSource` — muestrea los mismos 6 CSV reales de OLTARIS que
`GCR_SEP_Sim` (copiados a `data/`, no symlink, mismo motivo que allá:
Windows), vía `SpectrumSampler.hh/.cc` (copiado sin modificar, archivo
autocontenido, mismo criterio de no compartir código entre los dos
proyectos Geant4). Comandos nuevos (`ICRP110PhantomGeneratorMessenger`,
directorio `/gun/`, disponibles en Idle, después de `/run/initialize`):

```text
/gun/species GCR_H|GCR_He|SEP_p
/gun/phase max|min
```

**Una sola especie por corrida:** a diferencia de `GCR_SEP_Sim` (que mezcla
H+He estocásticamente dentro de una corrida), aquí el scoring de dosis por
órgano pasa por `G4ScoringManager`/`ICRP110UserScoreWriter` (sin tocar),
que no distingue especies dentro de una misma corrida. Combinar especies
con sus pesos físicos `W[s] = π·R_esfera²·flujo_integrado[s]` (misma
fórmula que `RunAction.cc` de `GCR_SEP_Sim`, radio de esfera fuente ahora
vía `ICRP110PhantomConstruction::GetSourceSphereRadius()`, adaptado de
esfera a la media diagonal del cilindro) se hace **en Python**, leyendo el
`ICRP110.out` de cada corrida — ver `scripts/aggregate_organ_doses.py`.

**`scripts/run_organ_sweep.py`:** corre las 15 combinaciones fijas (3
especies/fase × 5 posiciones, ver el propio script) de forma secuencial —
`ICRP110UserScoreWriter` siempre escribe su salida en un nombre **fijo**
(`ICRP110.out`), así que cada corrida se archiva antes de lanzar la
siguiente. Requiere un `.map` uniforme ya generado con
`field/generate_uniform_map.py` (entorno `field/.venv`, no `geant4_env`):
un solo archivo de referencia a 1 T sirve para cualquier intensidad vía
`/spacecraft/fieldScale` (aquí, 10). Manifiesto + resume, mismo patrón que
`GCR_SEP_Sim/scripts/run_sweep.py` (ver advertencia de `--n-events` en el
docstring del script). Salida: `resultados_organo_sweep.csv`.

**`scripts/aggregate_organ_doses.py`:** reimplementa la integral trapezoidal
de `SpectrumSampler.cc` en Python puro (sin numpy) para `W[s]`, aplica
`w_R` (ICRP 103 Tabla A.3: protón/pion cargado = 2, alfa = 20 — **pondera
por la partícula primaria de la corrida, no por partícula-en-cada-paso**;
un neutrón secundario hereda el `w_R` del primario) y produce
`resultados_organo_agregados.csv` (dosis absorbida/equivalente por
`organo_id` y posición, GCR y SEP por separado — distinta semántica
temporal, Gy/día vs Gy/evento, no se suman) más
`resultados_riesgo_estocastico.csv` (la misma vista, filtrada a los 5
órganos de interés, emparejados por palabra clave sobre el nombre real de
`ICRPdata/.../AM_organs.dat` — advierte explícitamente si alguna palabra
clave no matchea nada, en vez de fallar en silencio). **Limitación:** el
fantoma es masculino; la dosis en tejido mamario de un fantoma masculino es
una referencia dosimétrica/geométrica, no equivalente al riesgo
epidemiológico de cáncer de mama documentado en mujeres.

`QGSP_BIC_HP` sigue siendo la physics list de este proyecto (no `Shielding`,
la del piloto `GCR_SEP_Sim`).
