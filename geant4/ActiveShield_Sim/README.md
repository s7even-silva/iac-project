# ActiveShield_Sim

Simulación GEANT4 del blindaje magnético activo real: nave cilíndrica ARSSEM
(5.6 × 10 m) + arreglo de bobinas Halbach + fantoma dosimétrico ICRP110, por
órgano. Es la geometría de producción para el artículo — reemplaza, cuando
esté lista, al placeholder de `../GCR_SEP_Sim/` (esfera + campo uniforme +
tejido homogéneo), que sigue existiendo como pipeline de referencia/piloto.

## Origen del código

Este proyecto **parte del ejemplo oficial de Geant4**
[`examples/advanced/ICRP110_HumanPhantoms`](https://github.com/Geant4/geant4/tree/master/examples/advanced/ICRP110_HumanPhantoms)
(copiado desde `useful-examples/ICRP110_HumanPhantoms/` de este repo, que a su
vez viene de la instalación conda de Geant4 11.4.2). `README_ICRP110_original.md`
es el README original del ejemplo, sin modificar, para referencia.

**Por qué partir de aquí y no de `GCR_SEP_Sim/`:** `ICRP110PhantomConstruction`
ya trae su propio `World` armado y el fantoma de 142 órganos (vóxeles reales,
no una esfera de tejido homogéneo) funcionando de punta a punta — confirmado
corriendo `male.in` tal cual (20-1000 eventos, dosis por órgano correcta en
`ICRP110.out`). Es mucho más barato agregar la nave y las bobinas como
volúmenes hijos de ese `logicWorld` ya existente, que extraer la lógica de
vóxeles de este ejemplo e insertarla dentro del `DetectorConstruction` de
`GCR_SEP_Sim` (que no fue diseñado para alojar un fantoma parametrizado).

## Estado actual (2026-09-07)

Partiendo del ejemplo oficial (fantoma + su `World` original de aire),
validado en este repo:

- Compila con el mismo toolchain que `GCR_SEP_Sim` (`g++`/`x86_64-conda-linux-gnu-c++`
  de `geant4_env` + `CMAKE_PREFIX_PATH="$CONDA_PREFIX"`, ver comandos abajo).
- `ICRPdata` (~52 MB, datos de los fantomas AM/AF) se descarga solo en el
  primer build vía `ExternalProject_Add` en `CMakeLists.txt` — no hace falta
  copiarlos a mano ni versionarlos (están en `.gitignore` vía `ICRPdata/`).
- Corrida de prueba (`male.in`/`female.in`, pencil beam de protones 250 MeV,
  20-1000 eventos) corre sin errores y produce `ICRP110.out` con dosis por
  los 142 órganos del fantoma, nombres legibles + masa + material.

**Ya implementado: nave ARSSEM como geometría estática** (`ICRP110PhantomConstruction.cc`):
- `World` agrandado de 2 m a 7 m de half-size (el original solo alcanzaba
  para el fantoma solo).
- `ShipHull`: `G4Tubs` de aluminio, radio 2.8 m, 10 m de largo total (eje Z).
- `ShipInterior`: `G4Tubs` de aire dentro del casco (radio y longitud menos
  5 cm de espesor de casco), donde eventualmente irán las bobinas Halbach y
  el campo magnético.
- El fantoma (`phantomContainer`) cuelga de `ShipInterior`, centrado en el
  eje del cilindro a media longitud (posición fija, sin barrido — decisión
  de equipo ya tomada, ver `CLAUDE.md`). El eje Z del cilindro coincide con
  el eje "de pie" del cuerpo (altura ≈1.78 m para el fantoma completo,
  calculada de 222 vóxeles × 8 mm en Z) — el fantoma queda de pie a lo largo
  del eje de la nave sin necesidad de rotarlo.
- Validado sin overlaps (`G4PVPlacement` con chequeo activo) para ambos
  fantomas, masculino y femenino, completos.

**Todavía no implementado: bobinas Halbach ni campo magnético.** `ShipInterior`
es aire vacío por ahora — el protón del pencil beam de prueba atraviesa el
casco de aluminio sin desviarse (dosis distinta a la corrida sin nave, como
se espera físicamente al agregar un blindaje pasivo de por medio).

## Diferencias clave frente a `GCR_SEP_Sim/` (a tener en cuenta al portar código)

- **Fuente de partículas:** este ejemplo usa `/gps/...` (General Particle
  Source, pencil beam por defecto) en vez de `G4ParticleGun` +
  `SpectrumSampler` con muestreo isotrópico en superficie esférica. Para
  reusar los espectros GCR/SEP y el muestreo isotrópico de `GCR_SEP_Sim`, hay
  que portar `SpectrumSampler` + adaptar `PrimaryGeneratorAction` (la fuente
  isotrópica deberá muestrear sobre la superficie del cilindro, no de una
  esfera — es un cambio real de la física de muestreo, no solo de geometría).
- **Scoring:** este ejemplo usa `/score/...` (mesh scoring, boxMesh 3D) +
  acumulación por órgano vía `ICRP110UserScoreWriter`, en vez del acumulador
  manual (`fEdep` en `RunAction`) de `GCR_SEP_Sim`. El CSV de salida
  (`resultados_dosis_sweep.csv`) tendrá que rediseñarse para tener una fila
  por (corrida, órgano) en vez de una fila por corrida — más columnas, más
  datos, pero es la granularidad que pide el análisis por órganos.
- **Physics list:** este ejemplo usa `QGSP_BIC_HP` (`ICRP110phantoms.cc`),
  mientras que `GCR_SEP_Sim/main.cc` usa `Shielding`. Son distintas — hay que
  decidir con el equipo cuál usar en el proyecto integrado antes de correr
  nada para el artículo (es uno de los parámetros que un revisor pide
  congelar explícitamente en Métodos).

## Próximos pasos (en orden)

1. ~~Agrandar el `World`~~ — hecho (7 m de half-size).
2. ~~Agregar el cilindro ARSSEM~~ — hecho (`ShipHull`/`ShipInterior`, fantoma
   centrado en el eje a media longitud, sin overlaps, geometría estática).
3. **Bobinas Halbach**: geometría de las bobinas (dimensiones aún sin definir
   por el equipo) + clase de campo custom (`G4MagneticField` derivado, no
   `G4UniformMagField` — el campo Halbach no es uniforme) para poder además
   scorear fluencia sobre el propio conductor (recomendado como el aporte de
   mayor valor/esfuerzo del paper).
4. **Portar** `SpectrumSampler`, adaptar `PrimaryGeneratorAction` (fuente
   isotrópica cilíndrica), y decidir si el barrido usa `run_sweep.py` de
   `GCR_SEP_Sim` apuntado aquí vía `--build-dir` (la maquinaria de
   resume/manifiesto/estadística es reusable tal cual) o una copia adaptada
   si el esquema de combinaciones cambia mucho (p. ej. parámetros del imán en
   vez de posición del astronauta).

## Cómo compilar y correr

Mismo entorno y mismo workaround de compilador que `GCR_SEP_Sim` (ver
`CLAUDE.md` en la raíz del repo):

    cd geant4/ActiveShield_Sim
    mkdir -p build && cd build
    cmake -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" ..
    make -j$(nproc)

Corrida de prueba (fantoma dentro de la nave ARSSEM, sin campo magnético
todavía — pencil beam de protones):

    ./ICRP110phantoms male.in
