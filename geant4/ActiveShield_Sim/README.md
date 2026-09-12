# ActiveShield_Sim

Simulación Geant4 para estudiar blindaje magnético espacial con fantoma
ICRP110 y dosis por órgano. Base: ejemplo oficial `ICRP110_HumanPhantoms`,
conservado en `README_ICRP110_original.md`; datos descargados durante CMake.

## Estado actual y decisiones (2026-09-08)

- Geometría del hábitat: cilindro cerrado, diámetro exterior **5.6 m**, largo
  exterior **10 m**, eje Z. Casco de **G4_Al, 1.5 cm**, tapas planas del mismo
  espesor. Es una referencia radiológica, no un diseño estructural de vuelo.
- Exterior **G4_Galactic** (vacío); aire del hábitat y materiales ICRP110
  conservados. Fantoma masculino o femenino, centrado por defecto;
  desplazable a lo largo del eje Z vía `/spacecraft/phantomPositionCm` y/o
  radialmente en XY vía `/spacecraft/phantomOffsetX|Y` desde 2026-09-10/11
  (ver sección "Dosis por órgano y equivalente" más abajo) — revierte la
  decisión previa de "sin barrido de posición". El barrido de producción
  actual usa **solo `phantomOffsetX`** (radial, el eje relevante para el
  campo real no uniforme de CREW HaT).
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
```

- `hullThickness`: positivo y menor de 100 cm, dimensiones exteriores fijas.
- `shipRadius`/`shipHalfLength`: radio y semilongitud del cilindro de la
  nave (por defecto 2,8m/5m, tamaño de Geom14/ARSSEM). CREW HaT usa
  4,5m de radio (referencia NIAC, diámetro de Starship); la semilongitud
  no tiene fuente para CREW HaT, se mantiene el valor por defecto como
  supuesto propio explícito (ver AGENTS.md).
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
  cambios). Habilita un barrido de posición — reversión de la decisión
  "sin barrido de posición" documentada en AGENTS.md, motivada por que el
  campo Halbach de CREW HaT ya validado es no uniforme. Un offset que
  saque el fantoma de `ShipInterior` se detecta por el chequeo de
  solapamiento nativo de Geant4, no por una validación propia.
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

## Dosis por órgano y equivalente (2026-09-10, campo real y bins desde 2026-09-11)

> **Nota para Bryam (2026-09-11):** esta sección es de Eddy, trabajando en
> paralelo a CREW HaT/Elmer — resumen de lo que cambió para que no te
> agarre de sorpresa al hacer `git pull`:
> - **Tu trabajo no se tocó.** `shipRadius`/`shipHalfLength`/
>   `phantomOffsetX|Y` (los que agregaste el mismo día) se usan tal cual,
>   sin modificar — de hecho el barrido de este análisis corre a la escala
>   real de CREW HaT (`shipRadius=4.5m`) y usa `phantomOffsetX` como su eje
>   de posición principal, precisamente porque tu campo Halbach real es
>   no uniforme en esa dirección.
> - **Sí se usa tu campo real** (el arreglo de 8 bobinas,
>   `crewhat_halbach_array_pilot.json`, a su corriente de diseño máxima
>   1×10⁷ A/bobina) para este barrido — reemplazó un placeholder sintético
>   que se había usado un día antes.
> - **Cambio nuevo en `ICRP110PhantomPrimaryGeneratorAction`:** se agregó
>   `/gun/fixedEnergyMeV <valor>` (opcional, default deshabilitado) para
>   forzar una energía monoenergética exacta en vez de muestrear el
>   espectro — necesario para seguir la decisión de "bins de energía +
>   reponderación" que ya estaba en este archivo. No afecta nada si no se
>   usa ese comando (tus macros/pruebas siguen igual).
> - **El barrido resultante son 120 corridas** (3 especies × 8 bins de
>   energía × 5 posiciones), no una corrida única — se está repartiendo
>   60/40 entre Eddy y vos (`--only-positions`, ver más abajo) porque tu
>   laptop es más rápida. Si te llega una rama/PR pidiendo que corras tu
>   parte, es este barrido.
> - Detalle completo, con las tres rondas de cambios de diseño de este
>   mismo día, en `AGENTS.md` (sección "Dosis por órgano y equivalente,
>   riesgo estocástico").

Objetivo: dosis equivalente (Sv) en los 6 tejidos de mayor riesgo
estocástico de cáncer (ICRP 103 Tabla A.1, los `w_T=0.12`: colon, pulmón,
estómago, mama, médula ósea roja, tejidos restantes), en función de **dónde
está el fantoma dentro de la nave** (radialmente, no a lo largo del eje),
con el **campo real del arreglo de 8 bobinas de CREW HaT a su corriente de
diseño máxima** (1×10⁷ A por bobina, sin escalar) y **bins de energía
monoenergéticos + reponderación** (no muestreo continuo) por cada especie
en su fase más peligrosa (GCR en mínimo solar, SEP en Oct 1989). Ver
`AGENTS.md` para la historia completa (tres rondas: dos de reducción de
alcance, una que corrige un error real — la primera versión usaba muestreo
continuo, que ya estaba decidido no usar para producción).

**`ICRP110PhantomPrimaryGeneratorAction` reescrito:** ya no envuelve un
`G4GeneralParticleSource` — muestrea los mismos 6 CSV reales de OLTARIS que
`GCR_SEP_Sim` (copiados a `data/sources/oltaris/`, fuente versionada; el
CMake los copia planos a `data/` del build, ver `CMakeLists.txt`), vía
`SpectrumSampler.hh/.cc` (copiado sin modificar). Comandos nuevos
(`ICRP110PhantomGeneratorMessenger`, directorio `/gun/`, disponibles en
Idle, después de `/run/initialize`):

```text
/gun/species GCR_H|GCR_He|SEP_p
/gun/phase max|min
/gun/fixedEnergyMeV <valor>   # opcional -- MeV/amu (GCR_H|GCR_He) o MeV (SEP_p)
```

`fixedEnergyMeV` fuerza esa energía exacta en TODOS los primarios de la
corrida en vez de muestrear el espectro continuo de `SpectrumSampler` — es
lo que sigue la decisión de "bins + reponderación" que ya tenía AGENTS.md.
Omitirlo mantiene el muestreo continuo (default, usado por
`primary.mac`/demos, donde no aplica esa decisión de producción).

**Una sola especie Y UN SOLO bin de energía por corrida:** a diferencia de
`GCR_SEP_Sim` (que mezcla H+He estocásticamente dentro de una corrida), aquí
el scoring de dosis por órgano pasa por
`G4ScoringManager`/`ICRP110UserScoreWriter` (sin tocar), que no distingue
nada dentro de una misma corrida. Combinar `(especie,bin)` con sus pesos
físicos `W[s,bin] = π·R_esfera²·flujo_integrado_del_bin[s,bin]` (misma
fórmula que `RunAction.cc` de `GCR_SEP_Sim`, generalizada a un sub-rango de
energía por bin en vez de todo el espectro) se hace **en Python**, leyendo
el `ICRP110.out` de cada corrida — ver `scripts/aggregate_organ_doses.py`.

**`scripts/energy_bins.py`:** calcula, por especie, 8 bins log-espaciados
(decisión 2026-09-11, evaluado contra 5/10 bins y distinto N/corrida por el
costo en tiempo) dentro del rango de energía que cubre >99,9% del
flujo/fluencia real de cada espectro (calculado de los CSV reales — GCR_H y
GCR_He: 10–1×10⁵ MeV/amu; SEP_p: 0,01–300 MeV — no el rango tabulado
completo de OLTARIS, que tiene colas irrelevantes), con energía
representativa = media geométrica de los bordes del bin y peso físico real
por integral trapezoidal restringida a ese sub-rango.

**`scripts/run_organ_sweep.py`:** corre las **120 combinaciones fijas** (3
especies/fase × 8 bins de energía × 5 posiciones radiales `phantomOffsetX`
= 0/1/2/3/4 m, Y fijo en 0) de forma secuencial — `ICRP110UserScoreWriter`
siempre escribe su salida en un nombre **fijo** (`ICRP110.out`), así que
cada corrida se archiva antes de lanzar la siguiente. Nave a escala real de
CREW HaT (`shipRadius=4.5m`, `shipHalfLength=5m`, fijos en la macro).

**Campo de producción: Elmer FEM a escala real (2026-09-11), no
Biot-Savart.** `--field-map`/`--coil-geometry` ya traen default apuntando
a `field/production/` (versionado en git, ver más abajo) — no hace falta
pasarlos ni generar nada si clonaste el repo después de este cambio. Por
qué se cambió de Biot-Savart a Elmer: ver AGENTS.md, "Error de campo vs.
error de dosis en Elmer, y extensión a escala real" — en corto,
Biot-Savart sobreestima la dosis 36-48% en esta geometría porque trata
cada bobina como un filamento delgado, no como el winding pack real.
El `.map` de Biot-Savart anterior (`field/production/crewhat_niac_max.map`)
se conserva para comparación explícita
(`--field-map ../field/production/crewhat_niac_max.map`).

**Corrección (2026-09-12): el arreglo de 8 bobinas es CORC (winding pack
0,67m), no la cinta 12mm (1,43m).** Descubierto revisando el JSON fuente
al preparar estos archivos para `field/production/` — ver AGENTS.md para
el detalle completo. No afecta la validez de la comparación
Biot-Savart-vs-Elmer (ambos usan la misma geometría CORC), pero si algún
resultado se reporta como "cinta 12mm", es un error — todo lo del arreglo
hasta ahora es CORC. El GDML se llama `crewhat_corc_array.gdml` en
`field/production/`, no `halbach_array.gdml`, precisamente para que este
error no se repita.

`/spacecraft/coilGeometry` (la masa/material real de las bobinas, no solo
su campo) también se importa por defecto ahora — decisión de equipo ya
registrada en AGENTS.md ("Mantener material de devanados..."), que el
lanzador nunca había seguido hasta este cambio. `--no-coil-geometry` para
comparar sin ellas.

**`field/production/`:** único lugar donde `.map`/GDML de producción sí
se versionan (excepción deliberada en `.gitignore`, `!field/production/**`
— `field/generated/` sigue sin versionarse). 12MB: los dos `.map`
(Elmer y Biot-Savart) con sus manifiestos SHA256, el GDML CORC del
arreglo con su manifiesto/materiales/config fuente. Suficiente para
clonar el repo, compilar, y correr `run_organ_sweep.py` sin instalar
Elmer/Gmsh ni regenerar nada — ver `field/production/README.md`.

Manifiesto + resume, mismo patrón que `GCR_SEP_Sim/scripts/run_sweep.py`.
`--only-positions` reparte el barrido en equipo por posición completa
(cada posición trae sus 24 combinaciones de especie×bin) — ej.
`--only-positions 2,3,4` = 72 corridas (60%), `--only-positions 0,1` = 48
corridas (40%); `aggregate_organ_doses.py --results a.csv b.csv` junta los
CSV de ambas personas en una sola pasada (acepta varios archivos/patrones
glob). Salida: `resultados_organo_sweep.csv`.

**Costo por corrida, NO uniforme entre bins de energía (medido
2026-09-11, 14 hilos, con coilGeometry, 10000 eventos reales, GCR_H,
posición 0):** 21,6s (bin0, 17,8 MeV/amu) → 21,8s (bin1) → 34,1s (bin2) →
72,6s (bin3) → 275,3s (bin4, 1778 MeV/amu) → 730,4s (bin5, 5623 MeV/amu)
— cada bin tarda ~2,3-2,7x el anterior; los bins 6-7 (17780-56230 MeV/amu)
probablemente son los más caros de los 8. Cualquier presupuesto de
tiempo para el barrido completo debe usar esta curva, no un promedio
plano — la cifra anterior de este documento (~12,5s de overhead fijo +
~0,045s/evento, medida sin bobinas ni en los bins de mayor energía) ya
no es representativa de la configuración de producción actual.

**`--threads` (2026-09-11, default: todos los núcleos detectados):**
antes de este flag, `ICRP110phantoms` corría cada corrida con el default
de 4 hilos hardcodeado en `ICRP110phantoms.cc` (`SetNumberOfThreads(4)`),
sin que este lanzador lo sobreescribiera. Verificado en una máquina de 14
núcleos, mismo macro y semilla: dosis final **idéntica bit a bit** entre
1, 4 y 14 hilos (`ICRP110UserScoreWriter` funde correctamente los
resultados de los hilos worker de Geant4 MT — no es un dato asumido, se
comparó `ICRP110.out` de las tres corridas), con ~1,9x más rápido a 3000
eventos y ~1,33x a 10000 eventos yendo de 1 a 14 hilos (la ganancia
depende de cuánto pesa el overhead fijo de carga de ICRPdata, que no
paraleliza, frente al `/run/beamOn`, que sí). `/run/numberOfThreads` es
comando PreInit — el macro lo pone antes de `/run/initialize`.

**`--repeats N` (2026-09-11, default 1):** repite las 120 combinaciones N
veces con semillas distintas (`--repeats 5` = 600 corridas), mismo patrón
que `GCR_SEP_Sim/scripts/run_sweep.py`. Resume indexa por `(index,
repeticion)`. **Orden repetición-mayor siempre** (no un flag): termina
todas las combinaciones de la repetición 0 antes de empezar la 1 — da un
primer resultado completo mucho antes de terminar todo el barrido.
Necesario si se quiere media/std/IC95% por combinación — sin esto solo
hay una estimación puntual por (especie,bin,posición), sin barra de
error. `aggregate_organ_doses.py` calcula esa estadística entre
repeticiones en `resultados_riesgo_estocastico_repeticiones.csv` (con
`--repeats 1` imprime aviso y deja std/CV en blanco, no falla).

**`scripts/aggregate_organ_doses.py`:** usa `energy_bins.py` para los pesos
`W[s,bin]`, aplica `w_R` (ICRP 103 Tabla A.3: protón/pion cargado = 2, alfa
= 20, por especie no por bin — **pondera por la partícula primaria de la
corrida, no por partícula-en-cada-paso**; un neutrón secundario hereda el
`w_R` del primario) y produce `resultados_organo_agregados.csv` (dosis
absorbida/equivalente por `organo_id` sin agrupar y posición radial
`offset_x_m`, GCR y SEP por separado — distinta semántica temporal, Gy/día
vs Gy/evento, no se suman) más `resultados_riesgo_estocastico.csv` (las 6
categorías ICRP103 w_T=0.12, cada una agrupando varios `organo_id` en un
solo valor **ponderado por masa** — no una fila por `organo_id` como en la
versión anterior de este script). Médula ósea roja: cruza
`AM_organs.dat`/`AM_spongiosa.dat`/`OrganMasses.dat` reales (19 sitios
esqueléticos por su fracción RBM) — masa calculada (1,170 kg) coincide
exactamente con el valor de referencia ICRP para el adulto masculino.
"Tejidos restantes": agrupa 14 categorías anatómicas (suprarrenales, vías
respiratorias extratoracicas, mucosa oral, tráquea, vesícula biliar,
intestino delgado, corazón, riñón, ganglios linfáticos, músculo, páncreas,
próstata, bazo, timo) en un solo valor. Ambas agrupaciones EXCLUYEN
entradas con "contents" (heces, contenido gástrico, sangre en cámaras del
corazón) por ser material transitorio, no tejido vivo — decisión de
modelado marcada explícitamente en el script, no una convención ICRP
verificada. **Limitación:** el fantoma es masculino; la dosis en tejido
mamario de un fantoma masculino es una referencia dosimétrica/geométrica,
no equivalente al riesgo epidemiológico de cáncer de mama documentado en
mujeres.

**Physics list: `Shielding`, no `QGSP_BIC_HP`.** Corregido en el merge de
2026-09-11 (rama paralela de Bryam) — `ICRP110phantoms.cc` cambió de
`QGSP_BIC_HP` a `Shielding` vía `G4PhysListFactory` el mismo día que este
trabajo de Eddy, en un archivo que esta sección no tocó; misma physics
list que el piloto `GCR_SEP_Sim`. Recompilado y verificado con `ctest`
tras el merge (2 tests, ambos pasan).
