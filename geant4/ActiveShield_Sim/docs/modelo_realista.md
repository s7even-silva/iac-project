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
