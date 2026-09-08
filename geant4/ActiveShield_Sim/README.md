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
  de equipo ya tomada, ver `AGENTS.md`). El eje Z del cilindro coincide con
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
3. **Bobinas Halbach** — el paso más grande, con tres piezas independientes
   que hay que conectar explícitamente (Geant4 no las relaciona solo):

   a. **Geometría de las bobinas** (volúmenes reales, material superconductor
      real): **pendiente definir con el equipo — número de bobinas (6-8),
      dimensiones de cada una, y su posición/arreglo dentro de `ShipInterior`
      (radio al que se colocan respecto al eje, si van pegadas al `ShipHull`
      o a otro radio, espaciado angular).** Sin esto no se puede escribir el
      `G4Tubs`/`G4Torus` de cada bobina ni la clase de campo del punto (b).
      No es solo estética: con material real (REBCO/CORC + crióstato), estas
      bobinas son **blindaje pasivo incidental** — absorben radiación
      primaria pero también la fragmentan en secundarios (neutrones,
      fotones de captura, espalación) que pueden llegar al fantoma. Ignorar
      esto subestima la dosis real; es el mismo efecto que SR2S documentó
      como hallazgo central para blindaje activo en general. **El material
      de las bobinas debe estar en la simulación, no solo el campo que
      producen** — son dos cosas independientes en Geant4 (ver siguiente
      punto) y ambas hacen falta para una dosis creíble.

   b. **La función de campo en sí** — clase custom derivada de
      `G4MagneticField` (no `G4UniformMagField`, que solo puede devolver un
      vector constante). En cada paso de una partícula cargada, Geant4 llama
      a `GetFieldValue(point, bField)` y usa lo que devuelva para curvar la
      trayectoria (integración de la ecuación de Lorentz vía
      `G4Mag_EqRhs` + un stepper como `G4ClassicalRK4`) — es el mismo
      mecanismo que ya usa `GCR_SEP_Sim` con el campo uniforme, solo que la
      fórmula que hay que escribir es más compleja. Dos formas de obtener
      esa fórmula, ambas válidas (la diferencia es dónde vive el cálculo
      original, no si Geant4 "simula" el campo o no — en ambos casos Geant4
      solo evalúa una función ya calculada):
      - **Analítica dentro de Geant4**: un Halbach dipolar tiene expresión
        cerrada razonable (superposición de la contribución de cada bobina,
        cada una rotada según el ángulo de magnetización Halbach
        `θ_mag = 2·θ_posición`). Se implementa entera en C++, se evalúa en
        tiempo real durante el tracking, sin depender de ningún archivo
        externo — es la opción "más nativa" posible, y la que más
        diferenciaría el proyecto de los antecedentes encontrados (ninguno
        hace esto, ver más abajo).
      - **Tabulada/importada** (camino más probable, según decisión del
        equipo — 2026-09-07): un script externo (Python, Biot-Savart
        numérico, o un FEM tipo lo que antes se planeaba en ANSYS)
        precalcula `B(x,y,z)` en una grilla y Geant4 la lee con
        `G4CachedMagneticField` + interpolación. Más simple de implementar
        y más flexible si la geometría de bobinas termina siendo compleja
        (no puramente dipolar), a costa de que el cálculo del campo en sí
        no vive dentro de Geant4. **Importante:** esto sigue contando como
        "Halbach modelado en Geant4" en el sentido que importa para el
        punto 1 de la geometría (bobinas reales + campo no uniforme en vez
        del placeholder uniforme) — lo que cambia es solo cuánta "novedad
        nativa" se puede reclamar en el punto 6 (ver tabla de seguimiento
        en `AGENTS.md`): con campo importado, el diferenciador real pasa a
        depender más del scorer de fluencia sobre el conductor que de cómo
        se calculó el campo.

   c. **Asociar el campo a una región**: una vez con (a) y (b), se registra
      el campo en un `G4FieldManager` asignado al volumen donde debe actuar
      (`ShipInterior` completo, o una región más acotada) — igual que ya
      hace `DetectorConstruction::Construct()` en `GCR_SEP_Sim` con
      `SetFieldManager(localFieldMgr, true)`. Sin este paso, tener la
      fórmula del campo (b) no tiene ningún efecto: Geant4 solo evalúa el
      campo en las regiones donde explícitamente se le dijo que lo hiciera.

   Una vez con (a)-(c), agregar el scorer de fluencia sobre el volumen de
   cada bobina (recomendado como el aporte de mayor valor/esfuerzo del
   paper — relaciona directamente la Sección 1 (diseño del imán) con la
   Sección 2 (dosis), algo que hoy no existe en el índice del artículo).

   **Antecedentes investigados (2026-09-07) — dónde queda la novedad real:**
   Ninguno de los estudios de blindaje magnético activo espacial encontrados
   modela el campo Halbach de forma nativa (analítica o Biot-Savart evaluada
   en cada paso del tracking) dentro de Geant4 — el patrón dominante en la
   literatura es calcular el campo *fuera* e importarlo, o usar un campo
   uniforme confinado por volumen simple:
   - **CREW HaT** ([Frazer et al. 2022, arXiv:2209.13624](https://arxiv.org/abs/2209.13624))
     — la referencia que el equipo consideraba "calcada": calcula el campo
     del Halbach Torus vía Biot-Savart + Runge-Kutta 4º orden en un
     **trazador propio, fuera de Geant4** (basado en Desiati & Zweibel, ApJ
     2014). Geant4 se usa **por separado**, solo para el cálculo final de
     dosis con un phantom dentro de una esfera de aluminio simple — sin
     evidencia de que la geometría de las bobinas esté dentro de esa corrida
     de Geant4. Es decir, ni siquiera CREW HaT hace lo que el Plan A
     propone; usa dos herramientas desacopladas.
   - **ARSSEM** ([Battiston et al., arXiv:1209.1907](https://arxiv.org/pdf/1209.1907))
     — mismo nombre que la nave elegida por el equipo (no es coincidencia
     casual con el plan del curso, revisar si es la fuente del nombre). Es
     el antecedente más cercano al scorer de material de bobinas: modela
     un arreglo Halbach de 12 bobinas "Double Helix" con material real
     (Al, cinta YBCO, cable MgB2) y descompone la dosis en (1) solo campo,
     (2) solo material de bobinas, (3) con relleno adicional — casi
     exactamente el diferenciador que se buscaba. Pero usa **GEANT3, no
     GEANT4**, y el campo está confinado uniformemente a los volúmenes de
     las bobinas, no una fórmula Halbach analítica real acoplada al stepper.
   - **SR2S** ([Vuolo et al. 2016, Life Sciences in Space Research](https://www.sciencedirect.com/science/article/abs/pii/S221455241600002X))
     — el antecedente más fuerte en **Geant4 real** (vía interfaz GRAS):
     modela un toroide MgB2 con material real de bobinas (Cu, Al, Ti, MgB2)
     y estructura de soporte, cuantificando "por primera vez" (su propio
     abstract) el efecto de secundarios generados por el blindaje activo y
     la estructura de la nave. Topología toroidal, no Halbach, y sin scorer
     de fluencia diferenciado sobre el conductor mismo.
   - **Ambroglini, Battiston & Burger 2016** ([Frontiers in Oncology](https://pmc.ncbi.nlm.nih.gov/articles/PMC4896949))
     — confirma con bobinas YBCO modeladas como cilindros de cobre de
     111 μm + estructura de grafito: 22% de la reducción de dosis atribuida
     en partes iguales a campo y material pasivo de las bobinas.

   **Conclusión:** no se encontró ningún estudio que combine (a) geometría
   Halbach con material HTS/REBCO real, (b) campo Halbach calculado
   nativamente (analítico o Biot-Savart) dentro del stepper de Geant4, y
   (c) scorer de fluencia específico sobre el conductor, los tres en Geant4
   puro. Esa combinación específica sería una contribución incremental
   genuinamente novedosa frente a CREW HaT, ARSSEM y SR2S, y debe citarlos
   exactamente así en la introducción/discusión del paper (dónde se sitúan
   y qué le falta a cada uno frente a lo que este proyecto propone).

   **Actualización (2026-09-07):** el equipo ya decidió que el Halbach se
   modela con geometría real dentro de Geant4 — no el placeholder
   `G4UniformMagField` de `GCR_SEP_Sim`. Lo que sigue sin decidirse es si
   (b) se resuelve analítico (más "nativo", más cercano a lo descrito
   arriba como el vacío en la literatura) o importado de un cálculo externo
   (más simple de implementar, pero comparte el patrón dominante que ya
   usan otros estudios). Con campo importado, (a)+(c) —material real de
   bobinas + scorer de fluencia sobre el conductor— siguen siendo el
   diferenciador real frente a CREW HaT y ARSSEM (que no tienen scorer
   sobre el conductor) y frente a SR2S (topología toroidal, no Halbach);
   la novedad no depende exclusivamente de que (b) sea analítico.

4. **Portar** `SpectrumSampler`, adaptar `PrimaryGeneratorAction` (fuente
   isotrópica cilíndrica), y decidir si el barrido usa `run_sweep.py` de
   `GCR_SEP_Sim` apuntado aquí vía `--build-dir` (la maquinaria de
   resume/manifiesto/estadística es reusable tal cual) o una copia adaptada
   si el esquema de combinaciones cambia mucho (p. ej. parámetros del imán en
   vez de posición del astronauta).

## Cómo compilar y correr

Mismo entorno y mismo workaround de compilador que `GCR_SEP_Sim` (ver
`AGENTS.md` en la raíz del repo):

    cd geant4/ActiveShield_Sim
    mkdir -p build && cd build
    cmake -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" ..
    make -j$(nproc)

Corrida de prueba (fantoma dentro de la nave ARSSEM, sin campo magnético
todavía — pencil beam de protones):

    ./ICRP110phantoms male.in
