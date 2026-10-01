# Decisiones del modelo realista — actualizado 2026-09-08

Este documento distingue decisiones acordadas, cambios implementados y propuestas.
El devanado real y el mapa físico validado siguen pendientes. La conversión
geométrica y la importación de componentes de prueba ya están implementadas.

## Conversión y entorno implementados (2026-09-08)

Actualización de desarrollo: `field/generate_dh.py` añade un circuito Double
Helix de ensayo; `compute_field.py`, un mapa Biot–Savart regularizado de referencia.
No son el ensamblaje Geom14 ni una solución Elmer. La secuencia reproducible está
en la [guía del campo](../../../field/README.md); la propuesta 2A/4A/8A,
sus macros/costes y verificaciones con fuentes están en
[dominios y ruta Geom14](../../../field/DOMAINS.md). El planificador no ejecuta
el muestreo por bins ni demuestra convergencia automáticamente.

`field/` contiene el generador de malla y el conversor a GDML, con un JSON
explícito de elementos, densidades y fracciones másicas por grupo de volúmenes.
Se extraen superficies cerradas de tetraedros lineales y se conservan piezas
de distintos materiales. Geant4 las carga con `/spacecraft/coilGeometry`
directamente bajo `MagnetEnvelope`, sin superponer el mundo auxiliar del GDML.

Se creó `field/.venv` con Gmsh 4.15.2 y NumPy 2.3.3, separado de conda.
Versiones, hashes, configuración de mallado y masas quedan en manifiestos.
El entorno y las salidas son regenerables y están excluidos de Git. Esto
mejora la reproducibilidad; no garantiza identidad numérica entre plataformas
distintas ni fija aún el solver Elmer. La prueba usa Cu/Al, no REBCO ni DH.

Procedimiento, límites del formato, validación y siguientes pasos:
[guía de mallado y conversión](../../../field/README.md).

## Casco: referencia radiológica y diseño estructural

**Base adoptada en código:** aluminio elemental `G4_Al`, densidad nominal
2.70 g/cm³, espesor 1.5 cm (4.05 g/cm² a incidencia normal), incluido en las
tapas planas. Sustituye los 5 cm anteriores (13.5 g/cm²). Se conservan las
medidas exteriores del proyecto: diámetro 5.6 m, longitud 10 m. Con 1.5 cm,
la cavidad mide 5.57 m de diámetro y 9.97 m de longitud. La masa de esta
cáscara cerrada es aproximadamente 9.08 t, calculada por diferencia de los
volúmenes cilíndricos, sin equipos ni estructura secundaria. El programa
imprime la masa real calculada con el material Geant4.

**Justificación de referencia:** ARSSEM emplea para Geom01 una pared de
1.5 cm de Al, aproximadamente 4 g/cm², como comparación con blindaje activo
(capítulo 5, tabla 5.7). Adoptar ese espesor facilita una comparación
radiológica trazable; no valida las dimensiones del hábitat ni su resistencia.
[ARSSEM](https://arxiv.org/pdf/1209.1907).

**Para el diseño mecánico**, Al 2219 es un candidato razonable a investigar:
un concepto de hábitat de tránsito de NASA emplea placas de Al 2219 con
ortogrid y elementos de Al 7075. Ese diseño tiene dimensiones y geometría
propias, que no se trasladan automáticamente a esta nave.
[Estudio NASA](https://ntrs.nasa.gov/api/citations/20170002219/downloads/20170002219.pdf).

El modelo no debe denominarse «casco de Al 2219»: hoy usa Al elemental
homogéneo. Una aleación concreta necesitará composición y densidad verificadas;
un casco de vuelo necesitará presión, cargas de lanzamiento, uniones,
rigidizadores, tapas, fatiga y protección frente a micrometeoroides. No se ha
optimizado material o espesor. La interfaz `hullThickness` permite estudiar
sensibilidad sin editar C++, conservando el diámetro y largo exteriores.
No agregar equipamiento como espesor de Al sin justificar su masa y composición.

## Vacío y jerarquía

- `World` y `MagnetEnvelope`: `G4_Galactic`, aproximación de vacío Geant4.
- `ShipHull`: cáscara cerrada, diferencia entre cilindro exterior y cavidad.
- `ShipInterior`: aire, hermano del casco y contenido en `MagnetEnvelope`.
- Fantoma: dentro de `ShipInterior`; los materiales y huecos de aire ICRP110
  se conservan. «Cambiar aire a vacío» aplica al exterior, no a los pulmones
  ni a una cabina que se modela como presurizada.
- Bobinas, soportes y crióstatos externos: futuros hijos de `MagnetEnvelope`.
  Sus dimensiones deben comprobarse contra ese volumen y contra el casco.

La envolvente evita usar la cabina como contenedor del imán externo. No se
han inventado bobinas para llenar ese espacio. El aire de cabina mantiene
la aproximación original (1 kg/m³, fracciones másicas N/O de 0.8/0.2), no
una atmósfera certificada de misión.

## Campo: alcance global y límites del mapa

**Implementado:** clase `MagneticFieldMap`, interpolación trilineal,
`TabulatedMagneticField` derivada de `G4MagneticField`, conexión global mediante
`G4FieldBuilder` en `ConstructSDandField`. Los datos inmutables se comparten
entre hilos; cada hilo tiene su objeto de campo. No se evalúa Elmer durante
el transporte. Formato, comandos y controles en el README.

El campo global se aplica al vacío, casco, cabina, fantoma y futuras bobinas.
La decisión evita perder la desviación del primario antes de alcanzar la
nave y los campos de fuga en los extremos. Una frontera de material no es
una frontera del campo. Geant4 admite este registro global y clases de
campo definidas por el usuario.
[Guía Geant4](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/Detector/electroMagneticField.html).

**Extensión computacional:** semitamaño mínimo del mundo de 10 m por eje,
configurable. Con mapa, cada eje crece hasta al menos el máximo valor absoluto
de sus límites más 1 m; `MagnetEnvelope` deja 0.5 m respecto al mundo. Son
márgenes de alojamiento geométrico, no longitudes de decaimiento deducidas
para el imán. Se rechazan mapas que no sobrepasen el hábitat en los tres ejes.

**Limitación explícita:** fuera de la tabla se devuelve cero. Se registra
el máximo |B| de las caras, pero no existe todavía un radio de truncamiento
físicamente validado. Un mapa enorme pero grueso tampoco garantiza exactitud.
Antes de producción se debe:

1. Resolver una bobina y contrastar dirección, magnitud y simetrías con una
   solución independiente (por ejemplo Biot-Savart para corrientes prescritas).
2. Refinar malla FEM e interpolación, comprobando errores vectoriales y
   divergencia numérica. La interpolación trilineal no impone divergencia nula.
3. Ampliar el dominio FEM y el dominio exportado; comprobar convergencia de
   trayectorias y dosis por órgano, con estadística suficiente para detectar
   diferencias. El máximo |B| del borde por sí solo no mide el efecto acumulado.
4. Revisar la integral de B transversal a lo largo de trayectorias relevantes,
   incluidas las contribuciones exteriores omitidas y la rigidez mínima estudiada.
5. Ajustar tolerancias de integración y verificar estabilidad respecto a ellas.
   No imponer un límite de longitud de traza que sesgue silenciosamente la dosis.

Propuesta de aceptación numérica (no resultado conseguido): cambios de dosis
por dominio/interpolación por debajo de 1%, siempre que su incertidumbre
Monte Carlo permita resolver ese nivel. El equipo debe fijar el presupuesto
final de error. Conservar dominio, resolución, unidades, corriente, versión
del exportador y hash del mapa junto a cada resultado.

`G4CachedMagneticField` es una optimización que reutiliza evaluaciones cercanas;
no carga ni interpola archivos y no se ha usado. Un mapa físico FEM sigue
pendiente. Sin archivo, la ejecución indica explícitamente campo apagado.
`fieldScale=0` permite el control con el mismo dominio; escalar proporcionalmente
B solo corresponde a escalar corriente cuando el problema es lineal.

### Hallazgo pendiente (2026-09-30): la esfera fuente corta el arreglo de bobinas

**Qué se encontró:** `GetSourceSphereRadius()` (`ICRP110PhantomConstruction.cc`,
comentario: "same 20 cm margin as GCR_SEP_Sim") calcula el radio de la esfera
donde se generan los primarios como `diagonal_media_nave + hullThickness + 20cm`.
A escala de producción (`shipRadius=4.5m`, `shipHalfLength=5m`,
`hullThickness=1.5cm`) da **≈6.94 m**. Esta fórmula se heredó literalmente de
`GCR_SEP_Sim`, un proyecto hermano que nunca tuvo bobinas que considerar — no
hay evidencia de que se haya re-evaluado al incorporar el arreglo CREW HaT.

Extensión real de las bobinas, medida sobre los 24052 vértices de
`field/production/crewhat_corc_array.gdml`: **radio 5.67–10.34 m, z entre
−4.34 y +4.34 m**. La esfera de 6.94 m corta el arreglo: el 12.4% de los
vértices de las bobinas queda dentro de ella. El cascarón r≈6.94 m del mapa
Elmer tiene |B| medio de 0.98 T y máximo de 5.2 T, así que los primarios
nacen en una zona de campo intenso. Todo el rango está cubierto por el mapa,
por lo que el campo en el punto de nacimiento está bien representado.

**Por qué importa físicamente:** el blindaje magnético funciona porque,
fuera del campo, el flujo es isótropo y el campo crea direcciones
prohibidas (conos de Störmer) al entrar. Si una partícula se genera con
distribución isótropa en un punto que ya está dentro del campo, esas
direcciones prohibidas se pierden en el tramo exterior al punto de
nacimiento. La superficie fuente debería estar donde B sea despreciable
frente a la rigidez de las partículas de menor energía estudiadas.

**Mapa truncado en sus caras:** fuera de la tabla el código devuelve B=0,
pero en las caras del mapa |B| máx es 0.40 T (±x), 0.16 T (±y) y 0.26 T (±z).
No es un campo que se anule: cae de golpe a cero. Además el dominio Elmer usa
`AV = 0` en su frontera exterior (`case.sif`), lo que impide que el flujo
salga y probablemente eleva el campo cerca de esa frontera (a verificar
agrandando el dominio). Para mover la esfera fuera de la zona de campo hay
que regenerar el mapa Elmer con un dominio mayor; en esta máquina (5 GB de
RAM) no cabe, porque el solve a escala real anterior tuvo un pico de 7.3 GB.

### Hallazgo crítico (2026-09-30): todos los primarios apuntan exactamente al origen

`SampleIsotropicPosition()` (`ICRP110PhantomPrimaryGeneratorAction.cc`) fija
`dir = -onSphere`: cada primario sale de la esfera **apuntando al centro de
la nave**. El peso `W = π R² × flujo` de `aggregate_organ_doses.py` supone
fluencia isótropa dentro de la esfera (entrada con ley coseno, ver la
sección de bins más abajo). Con apuntado radial se obtiene en cambio un haz
convergente en el origen:

- Un fantoma en `offset_x_m=0` recibe prácticamente todos los primarios no
  desviados. Uno desplazado solo recibe las rectas que pasan por el origen y
  lo cruzan. Esto crea una dependencia artificial con la posición.
- En el centro, la dosis estimada crece aproximadamente con R², porque W
  crece como π R² y la fracción que acierta al fantoma no baja. **El
  resultado depende del radio de la esfera**, algo que con muestreo correcto
  no ocurre.

El campo del mapa de producción en el eje es **0.54 T en x=0, 0.54 T en
x=1 m y 0.55 T en x=2 m**. El campo no se cancela en el eje, así que la
hipótesis de `resultados/historico_barrido600_radial/LIMITACIONES_BARRIDO_600.md` §13 (cancelación
Halbach) queda descartada. El salto de dosis entre x=0 y x≥1 m se explica
por el bug de la malla de scoring (sección siguiente). El apuntado radial
es un problema aparte que infla todas las dosis, sobre todo en x=0.

**Corrección necesaria antes de citar dosis absolutas:** muestrear la
dirección entrante con ley coseno (`cosθ = sqrt(u)` respecto a la normal
interior) y mantener `W = π R² Φ`. Implementado como opción
(`/gun/angularDistribution cosine`, 2026-09-30). El default sigue siendo
`radial` hasta que el equipo decida. Opciones de costo en "Mejoras
propuestas".

### Bug crítico (2026-09-30): la malla de scoring no sigue al fantoma

La plantilla de `run_organ_sweep.py` fija `/score/mesh/translate/xyz 0. 0. 0. mm`
mientras `/spacecraft/phantomOffsetX` mueve el fantoma a 1–4 m. La malla
(±0.27 × ±0.14 × ±0.89 m) se queda en el origen, que con offset≥1 m es aire
de cabina (`matAir`, densidad 0.001 g/cm³). `ICRP110UserScoreWriter` asigna
cada voxel a un órgano por su índice, suponiendo malla y fantoma alineados.
Por eso **las filas con `offset_x_m ≥ 1` son energía depositada en aire,
etiquetada como órganos**. La relación de densidades tejido/aire (~1000)
coincide con la caída observada (×1000–×3000 en todas las categorías). Las
filas con `offset_x_m = 0` no están afectadas por este bug, pero sí por el
apuntado radial.

**Corregido (2026-09-30)** en `run_organ_sweep.py` y
`pilots/pilot_common.py`: `/score/mesh/translate/xyz {offset_x_mm} 0. 0. mm`.
**Verificado (2026-09-30)** con GCR_H de 1778 MeV, `fieldScale 0`, ley
coseno, 30000 eventos y semilla 201: la dosis por primario en x=1 m es
**0.91** veces la de x=0 (3.19e-14 frente a 3.50e-14 J/primario). Antes del
arreglo la relación era de ~1/1000. Unos 100 primarios cruzan el fantoma
en cada corrida (~10% de incertidumbre), así que 0.91 es compatible con
1. Las corridas con offset≥1 m del barrido de 600 (480 de 600) hay que
repetirlas. Los workers que ya están desplegados siguen usando la plantilla
vieja hasta que se actualice su imagen o su checkout. Prueba de aceptación: con `fieldScale 0` y el
muestreo corregido, x=0 y x=1 m deben dar dosis parecidas.

### Mejoras propuestas (2026-09-30, sin decisión de equipo)

**1. Muestreo, radio de la esfera y costo.** Con ley coseno, la fracción de
primarios cuya recta cruza el fantoma es ≈ Ā/(π R²). Ā es el área proyectada
media del fantoma, del orden de 0.5 m² (área de piel ~1.9 m² / 4, teorema de
Cauchy). Esto supone trayectorias rectas; el campo lo modifica.

| R esfera | fracción que cruza el fantoma | ×eventos vs R=6.94 m | fracción que toca el casco |
|---|---|---|---|
| 6.94 m (actual) | ~0.33% (1 de 300) | 1 | ~68% |
| 11 m (rodea bobinas) | ~0.13% (1 de 760) | ~2.5 | ~27% |
| 19 m (rodea el mapa actual) | ~0.044% (1 de 2300) | ~7.5 | ~9% |

El tiempo de CPU crece menos que el número de eventos, porque los primarios
extra casi no tocan material. Formas de evitar la penalización:

- **Sesgo de la fuente con pesos (recomendado).** Muestrear direcciones
  preferentemente hacia la nave y dar a cada primario el peso
  `pdf_real/pdf_sesgada`. Es insesgado aunque el campo curve la trayectoria
  (solo pierde eficiencia a baja energía) y hace el costo casi independiente
  de R. Requisito: que el scorer multiplique por el peso de la traza
  (`G4PSEnergyDeposit` lo hace; verificar con una prueba).
- **Dos etapas con archivo de espacio de fases.** Etapa 1: transporte desde
  la esfera grande hasta una superficie que envuelva el casco, guardando las
  partículas que la cruzan. Etapa 2: casco + fantoma a partir de ese archivo.
  La etapa 1 se reutiliza para las 5 posiciones del fantoma.
- **Monte Carlo inverso (`G4AdjointSimManager`): no apto aquí.** En Geant4
  11.4.2 solo existen modelos adjuntos electromagnéticos (ionización,
  bremsstrahlung, Compton, fotoeléctrico, dispersión múltiple). No hay
  procesos hadrónicos, que para GCR (fragmentación, neutrones secundarios)
  no son despreciables.

**Radio y malla de Elmer.** El criterio es que el ∫B·dl que queda fuera de la
esfera casi no desvíe a las partículas de menor energía (referencia: 0.05 T·m
desvían ~0.1 rad a un protón de 10 MeV). Procedimiento:
(a) mapa Biot-Savart en un dominio grande (barato; lejos de las bobinas
coincide con Elmer dentro de ~3%) para ubicar dónde |B| cae lo suficiente;
(b) dominio Elmer hasta ahí, con malla de aire gradual (fina cerca del
conductor y la nave, gruesa lejos) para contener la memoria;
(c) verificar que el campo interior no cambie al agrandar la frontera
`AV = 0`. Requiere una máquina con más de ~8 GB de RAM.

**2. Scorer por evento ("Camino A").** El atajo R=1 de la Fase 7 falla porque
S2 se acumula por voxel y la suma por órgano ignora la covarianza entre
voxels tocados por el mismo primario (piloto A: SE_within/s_between mediana
0.48). Solución: acumular la energía por órgano dentro de cada evento (el
organ ID ya está en el voxel del fantoma) y, en `EndOfEventAction`, llenar
S1/S2/N del órgano con el total del evento. Esto da el error estándar
correcto por órgano y categoría. El costo es una suma extra por paso más un
volcado por evento de ~140 órganos: pequeño frente al transporte. El
`FASE7_SE_CORRECTION_FACTOR` (ver `docs/bitacora/plan_estadistico.md`) es un
parche conservador hasta implementar esto.

**3. Perfil temporal de SEP (GOES).** La respuesta R[o,s,bin] ya es por
primario y por energía, así que cualquier espectro dependiente del tiempo se
combina en el post-proceso sin volver a simular. Usar los flujos de protones
de GOES (cada 5 min) del evento de octubre de 1989 para escalar el espectro
OLTARIS en el tiempo. Supone que la forma del espectro es constante, así que
hay que reportarlo como aproximación. Resultado: tasa de dosis (pico y
media) y dosis acumulada en función del tiempo.

**4. Biot-Savart vs Elmer: volver a medir antes de citar.** Comparación de los
dos mapas de producción (`field/production/*.map`): dentro de la nave,
Biot-Savart da 0.94–0.98 del campo de Elmer en los ejes x/y y cae a
0.88–0.61 hacia los extremos en z. El ∫B⊥·dl desde la esfera al centro
(400 direcciones) vale en promedio 0.97 del de Elmer (0.92 hacia los
extremos). Una diferencia de ~3% en poder de desvío no explica por sí sola el
"36–48% más dosis" de la bitácora. Esa cifra salió de una semilla, una
energía y una posición, con el apuntado radial, y no se debe citar.
**Medido de nuevo (2026-09-30)** con GCR_H de 562 MeV (cerca del corte del
escudo), x=0, bobinas incluidas, malla corregida y semillas 401/411/421
idénticas para ambos mapas, 40000 eventos cada una. Con ley coseno, la
dosis Biot-Savart/Elmer da **0.93 ± 0.08** (0.78, 0.97 y 1.04 por
semilla). Con apuntado radial, semilla 301 y 5000 eventos, da **1.03**.
No se reproduce el "+36–48%": a esta energía no hay diferencia de dosis
significativa entre los dos mapas, lo que coincide con la diferencia de
~3% en ∫B⊥·dl. La especie y la energía de la comparación original no
quedaron registradas, así que esto no la replica exactamente, pero
cualquier diferencia real tendría que venir de otro bin. Por los extremos el
escudo es débil: ∫B⊥·dl mínimo 0.42 T·m, frente a 3.25 de media.

**5. Q(L) en vez de w_R por especie.** No es un cambio de fórmulas: Q depende
del LET de cada partícula en cada paso, incluidos los secundarios, y el
scorer solo guarda energía. Implementación: un scorer que acumule
`edep × Q(L)` por paso, con L ≈ LET en agua (ICRP 60 Q(L), recomendado para
astronautas por ICRP 123), además de `edep`. Requiere volver a correr, así
que conviene incluirlo en la próxima tanda de producción. Motivo: w_R=20 para
He GCR de alta energía (LET bajo, Q≈1) sobreestima mucho, y los secundarios
de alto LET no reciben su propio peso.

**6. Ponderación ICRP103 incompleta.** (a) `aggregate_organ_doses.py` solo
aplica w_R; w_T=0.12 nunca se multiplica y no se calcula dosis efectiva.
(b) "Tejidos restantes" se pondera por masa (lo domina el músculo); ICRP103
usa la media aritmética de 13 órganos por sexo. (c) Solo se simula el
fantoma masculino. La dosis efectiva requiere promediar AM y AF
(`/phantom/setPhantomSex female` ya existe) e incluir los 15 w_T. Correr AF
duplica el cómputo. Una alternativa es simular AF solo en las posiciones y
bins que finalmente se reporten.

**Estado:** sin decisión de equipo. Orden sugerido: bug de la malla (1 línea)
→ ley coseno + sesgo de fuente → scorer por evento y Q(L) en el mismo cambio
de C++ → dominio de campo mayor → nueva producción (AM+AF). Los puntos 3 y
6(a)(b) son post-proceso y no necesitan volver a simular. El punto 4 sí:
son dos corridas pequeñas, una con cada mapa.

## Gmsh, Elmer, Python y geometría del imán

Decisión del equipo: calcular el campo externamente con **Gmsh + Elmer + Python**.
Compartir parámetros entre generador de geometría radiológica y electromagnética:
radios, longitudes, orientaciones, posiciones, vueltas, corrientes y materiales.
Las corrientes de una Double Helix deben seguir el devanado, no una corriente
axial arbitraria aplicada a la envolvente de la bobina.

Gmsh produce CAD/malla mediante su API; Elmer resuelve el problema de campo;
Python remuestrea sus vectores en la tabla regular. El ejemplo oficial
`mgdyn_steady_coils` es un punto de partida para el acople de solvers, no una
implementación de vuestro imán.
[Gmsh](https://gmsh.info/doc/texinfo/),
[Elmer](https://github.com/ElmerCSC/elmerfem/blob/devel/fem/tests/mgdyn_steady_coils/case.sif).

Por otra vía, los parámetros deben generar sólidos Geant4 o un GDML con
volúmenes cerrados y materiales explícitos. Importar el campo no importa masa;
importar una malla FEM no traduce automáticamente las propiedades de material.
Validar masa, composición, transformaciones y solapamientos. El modelo
radiológico puede agrupar capas muy finas si se justifica y valida esa
homogeneización, manteniendo estructura y crióstato cuando sean relevantes.
[Geant4 GDML](https://geant4.web.cern.ch/documentation/pipelines/master/bfad_html/ForApplicationDevelopers/Detector/Geometry/geomXML.html).

Geom13/Geom14 de ARSSEM emplean Double Helix; Geom14 refina la composición de
la cinta YBCO. Geom15 combina racetrack laterales con DH en los extremos y
otro presupuesto material. Recomendación pendiente de adopción: empezar con
una configuración basada en Geom14, indicando cualquier cambio a CORC/REBCO.
No presentar Geom15 como una mejora garantizada ni trasladar porcentajes de
reducción a nuestro fantoma/espectro. [ARSSEM, capítulo 5](https://arxiv.org/pdf/1209.1907).

Antecedentes adicionales para revisión bibliográfica:
[CREW HaT](https://arxiv.org/abs/2209.13624),
[SR2S, Vuolo et al.](https://www.sciencedirect.com/science/article/abs/pii/S221455241600002X),
[Ambroglini et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC4896949/).
El uso de un campo importado no determina por sí solo la novedad científica.
La afirmación de que no existe trabajo equivalente requiere una revisión
bibliográfica específica; no se considera demostrada aquí.

## Bins de energía y espectros físicos: decisión confirmada

**Acordado por el equipo:** simulaciones por bins de energía y reponderación
posterior. Ya no es una decisión abierta entre bins y muestreo continuo.
Es una decisión metodológica; todavía no existe el pipeline de producción
por bins. Los 1000 eventos de `male.in` son historias de partículas en una
prueba monoenergética, no 1000 simulaciones independientes del ambiente.

En cada especie s y bin i se estima una respuesta por órgano o:

    R[o,s,i] = energía depositada total / (masa del órgano × N[s,i])
    D[o] = suma sobre s,i de R[o,s,i] × W[s,i]

R está en Gy por primario simulado; W representa el número físico de primarios
que cruzarían la superficie fuente, en ese bin y especie, durante la exposición
(GCR), o durante el evento integrado (SEP). Para una respuesta monoenergética
se debe comprobar el error de aproximar todo el bin por una energía.

**Por «espectros reales» se entiende exports físicos trazables** de ISO-15390
(GCR) y ESP-PSYCHIC (SEP) en SPENVIS, no necesariamente mediciones. Los seis
CSV versionados en `GCR_SEP_Sim/data/sources/spenvis/` siguen etiquetados como
placeholders: max y min son idénticos. Cambiar a bins evita muestrearlos durante
el transporte, pero no los convierte en pesos físicos válidos.

Se pueden generar respuestas por energía mientras llegan los exports y luego
reponderarlas para ambas fases solares, conservando especie, geometría y
supuestos angulares. No repetir todo el transporte solo porque cambie el peso
espectral si esos supuestos siguen siendo válidos.

Para intensidad diferencial isotrópica j(E) por sr, una superficie cerrada S
y muestreo entrante con ley coseno, W_GCR = S × pi × T × integral_bin j(E)dE.
Para SEP usar la fluencia diferencial del evento y no multiplicar por tiempo.
No aplicar pi de nuevo si el export ya integra la magnitud angular apropiada:
hay que comprobar las unidades y su definición. MeV/nucleón y energía total
por ion son diferentes. Gy no se convierte en Sv cambiando solo la etiqueta;
la dosis equivalente requiere su ponderación radiobiológica definida.

La fuente de producción debe encerrar también el imán y el dominio exterior
relevante. No necesita tener la forma de la nave: una esfera envolvente con
muestreo angular correcto es válida. Si se cambia su área, actualizar W para
no atribuir un cambio de normalización a una mejora del blindaje.

Los bins no eliminan el Monte Carlo: siguen siendo aleatorias las interacciones
y, según la fuente, posiciones/direcciones. Fijar rango, bordes, especies,
eventos/bin y criterio de incertidumbre. Verificar refinamiento energético y
usar segundos momentos por historia o lotes independientes para incertidumbre
por órgano. Con bins independientes, Var(D)=suma W² Var(R); las incertidumbres
espectrales y numéricas son contribuciones adicionales. Cero depósitos en un
bin con pocos eventos no demuestra dosis nula. GCR limitado a p/He debe
reportarse como tal: no representa toda la contribución de iones pesados.

## Barrido y comparación pasiva

`GCR_SEP_Sim/scripts/run_sweep.py` no es un lanzador universal: espera el
binario `gcrsim`, sus comandos `/detector/...`, `/gun/model`, `/gun/phase` y
un CSV escalar por corrida. `--build-dir` cambia dónde los busca, no adapta
las interfaces. Aquí se usa `ICRP110phantoms`, GPS y salida por órgano.

Reutilizar semillado/manifiesto/reanudación como diseño; crear un lanzador de
este proyecto cuando se definan los bins y configuraciones. El identificador
de una corrida deberá incluir especie, energía, geometría/materiales, mapa,
escala, semilla y N; no saltar resultados antiguos solo por un índice ordinal.

**Evaluación de esfuerzo, no implementación solicitada del blindaje pasivo:**
una capa cilíndrica cerrada de polietileno es una extensión geométrica acotada;
se puede añadir como volumen separado, con material y espesor configurables,
sin reescribir el campo ni el fantoma. La geometría es la parte sencilla;
la comparación a igual masa y el transporte estadístico requieren más trabajo.
El código pasivo del piloto es esférico: no se copia sin adaptación.
Polietileno es un candidato por su contenido en hidrógeno, no un reemplazo
automático del casco estructural.
[Investigación NASA](https://techport.nasa.gov/projects/88568).

Propuesta de matriz (todavía no implementada; falta el ensamblaje de bobinas real):

| Caso | Casco | Bobinas/material | Campo | Capa pasiva adicional |
|---|---|---|---|---|
| A | Sí | No | No | No |
| B | Sí | Sí | No | No |
| C | Sí | Sí | Sí | No |
| D | Sí | No | No | Sí |
| E (híbrido) | Sí | Sí | Sí | Sí |

B frente a C aísla activar el campo con el mismo material; A frente a D
mide la capa adicional; C frente a E mide añadir esa capa al sistema activo.
Comparar D frente a C exige declarar masas totales, densidades areales y
cobertura. El casco ya es blindaje pasivo estructural en todos los casos.
No etiquetar una capa de masa distinta como una comparación a igual masa.

## Verificación de este cambio

Verificado con Geant4 11.4.2 en `geant4_env`:

- Compilan `ICRP110phantoms`, `ICRP110standalone` y la prueba del mapa.
- CTest `field_map`: pasa interpolación, unidades, caras, puntos fuera del
  dominio, escala cero/no nula y rechazo de archivos inválidos.
- Fantoma masculino completo sin mapa: 2 protones desde -6 m; la traza
  confirma vacío exterior → casco → interior.
- Fantoma femenino completo, 2 hilos, mapa sintético constante de 10 µT:
  2 protones; desviación transversal de aproximadamente -0.0211 mm al
  alcanzar el casco (antes de entrar en él), frente a cero sin campo.
- Mapa sintético de límites ±12 m: mundo ampliado a semilados de 13 m.
  Con `fieldScale 0`, inicialización y chequeo recursivo hasta el contenedor
  del fantoma completos, sin solapamientos detectados.
- Masa analítica impresa del casco: aproximadamente 9076.4 kg con la densidad
  de `G4_Al` instalada (2.699 g/cm³; 9079.8 kg usando 2.700 g/cm³).

Los mapas de prueba son sintéticos y no se presentan como resultados del
escudo. Estas verificaciones no validan la dosis final ni sustituyen los
estudios de convergencia del campo FEM y la estadística por órgano.
