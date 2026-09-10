# Elmer: dominio exterior y corriente de la Double Helix

Actualizado 2026-09-09. Esta validación corresponde al **piloto DH de tres
vueltas**, sección circular de radio 12 mm y corriente de 100 A. No valida
el arreglo completo Geom14 ni el máximo de campo dentro de una cinta HTS.

## Dos problemas independientes

1. `mesh_swept_air.py` rodea el conductor con un tubo de aire. Su radio no
   puede superar la curvatura de los retornos sin autointersecciones. Imponer
   `A=0` en esa superficie próxima no representa adecuadamente el espacio
   exterior. Aumentar el número de tetraedros no aleja esa frontera.
2. En `CoilSolver.F90`, `ChooseFixedBulkNodesNarrow` y `ChooseCoilCut`
   recorrían todos los elementos volumétricos, incluidos los del aire.
   Los tetraedros del aire pueden unir candidatos de cortes separados del
   devanado. El parámetro `Single Coil Cut` por sí solo no lo evita: su
   coloreado de conectividad también recorría el aire. La conclusión anterior
   de que este parámetro estaba descartado por funcionar un toro sin él era
   insuficiente para una doble hélice.

Se contrastó el mismo conductor con y sin aire: al resolver solo el conductor,
la mediana de la densidad elemental fue aproximadamente 226.766 A/m² para
100 A (coherente con el área poligonal de la sección). Con aire y la selección
original, cambiar únicamente a `Desired Coil Current=100` no lo resolvió.
Con la configuración histórica de normalización puntual a 221.048,5 A/m²,
la mediana elemental después de la corrección de divergencia era solo
43.827 A/m², aunque la magnitud nodal conservaba el valor pedido.

La corrección restringe esos tres recorridos a `GetNOFActive()` y
`GetActiveElement(t)`. El caso mantiene `Single Coil Cut=True`, prescribe
**corriente total** (`Desired Coil Current=100`) y desactiva la normalización
puntual de magnitud (`Normalize Coil Current=False`). No se ajusta la corriente
para forzar coincidencia con Biot–Savart. La corriente corresponde al circuito
cerrado, no a 100 A repartidos entre todas las vueltas.

Fuente inspeccionada: [CoilSolver de Elmer, revisión fijada](https://github.com/ElmerCSC/elmerfem/blob/063e7e9f0bd647386f8f3b14e86cd7cff9c7d895/fem/src/modules/CoilSolver.F90).
El cambio es **local del proyecto**, no una corrección oficial ya incorporada
por Elmer. `build_coilsolver.py` verifica el SHA256 del original, conserva el
original y su licencia LGPL, compila `CoilSolverRestricted.so` con `elmerf90`
y registra hashes. No modifica la biblioteca instalada. Debe recompilarse
con el wrapper de la misma instalación de Elmer que ejecutará el caso.

## Mallado que conserva los tetraedros del conductor

`mesh_exterior.py` toma el `.msh` de **solo conductores**, extrae sus
superficies trianguladas, crea una caja exterior independiente y malla solo
el aire mediante HXT. Restaura los tetraedros originales del conductor;
no vuelve a triangular el CAD helicoidal. Admite varios grupos conductores.

Antes de publicar el resultado comprueba que no cambien los nodos ni las
caras de la interfaz, que la frontera del aire sea exactamente la caja más
las interfaces y que su volumen sea caja menos conductores. Los grupos de
entrada se conservan por nombre, con IDs consecutivos; aire y frontera
exterior reciben los siguientes IDs. Revisar siempre `mesh.names` de ElmerGrid.
Se requieren conductores separados, cerrados y sin intersecciones, en metros.

`--padding` es la distancia de cada cara de la caja a los límites del conjunto
de conductores; **no** es un radio desde el centro ni el semilado del mapa
Geant4. `--air-size` controla el tamaño máximo del aire, no la sección del
conductor ni el paso del mapa final. Puede aumentarse el dominio sin engrosar
el tubo junto al devanado. Para un estudio de convergencia, variar primero
padding manteniendo tamaños y puntos de comparación; después refinar tamaños.

La optimización usa por defecto `--optimize-threshold 0.01` para evitar que
HXT dedique un tiempo excesivo a elementos muy alargados impuestos por la
interfaz. **No es una tolerancia del campo ni una garantía de calidad**:
el manifiesto registra los percentiles de `minSICN`; quedan elementos de
baja calidad y debe comprobarse la convergencia FEM. La opción y las entidades
discretas están descritas en el [manual de Gmsh](https://gmsh.info/doc/texinfo/gmsh.html).
El presupuesto de memoria del arreglo completo aún no está validado; ejecutar
con `timeout` y conservar el log. Un timeout no certifica un límite matemático.

También se corrigieron los IDs duplicados de tetraedros y triángulos en
`mesh_swept_air.py`: los identificadores deben ser únicos en todo el archivo,
no reiniciarse por cuerpo. Las mallas tubulares anteriores deben regenerarse;
Gmsh descartaba elementos duplicados al releerlas. Este arreglo de exportación
no convierte el dominio tubular en un dominio exterior válido.

## Secuencia del piloto desde la raíz del repositorio

```bash
# Elmer ya instalado mediante scripts/install.sh --with-elmer.
# Descargar SOLO el fuente fijado y compilar el módulo local.
python3 field/build_coilsolver.py
# Sin red: añadir --source /ruta/al/CoilSolver.F90 de la revisión indicada.
# Si Elmer está en otro prefijo: --elmerf90 /prefijo/bin/elmerf90.

field/.venv/bin/python field/generate_dh.py \
  field/examples/dh_pilot.json field/generated/elmer_dh
field/.venv/bin/python field/mesh_swept.py \
  field/generated/elmer_dh/current_path.json \
  field/generated/elmer_dh/conductor.msh --longitudinal-step 0.04

timeout 300 field/.venv/bin/python field/mesh_exterior.py \
  field/generated/elmer_dh/conductor.msh \
  field/generated/elmer_exterior/domain.msh --padding 1.3 --air-size 0.15

cp field/examples/elmer_pilot.sif field/generated/elmer_exterior/case.sif
cp field/generated/elmer_plugin/CoilSolverRestricted.so field/generated/elmer_exterior/
cd field/generated/elmer_exterior
~/.local/elmerfem/bin/ElmerGrid 14 2 domain.msh -out elmer_mesh
# Verificar mesh.names: dh_winding=1, air=2, outer_boundary=3.
OMP_NUM_THREADS=1 timeout 600 ~/.local/elmerfem/bin/ElmerSolver case.sif
cd ../../..

field/.venv/bin/python field/compare_elmer.py \
  field/generated/elmer_exterior/elmer_mesh/elmer_pilot_air_t0001.vtu \
  field/generated/elmer_dh/current_path.json \
  field/examples/dh_validation_probes.json \
  field/generated/elmer_exterior/comparison.json
```

Los valores anteriores son de diagnóstico, no parámetros aprobados de producción.
El `.sif` ahora aborta si sus sistemas lineales no convergen, para evitar aceptar
un VTU como solución válida solo porque se escribió. Para varios circuitos hacen
falta cuerpos/componentes con sus corrientes y orientaciones; no basta copiar
el `.sif` de una bobina al arreglo. No modificar ni escalar las corrientes para
obtener una intensidad objetivo sin cerrar antes la ficha del imán.

## Qué significa comparar con Biot–Savart

La **ley** de Biot–Savart no es una aproximación de campo lejano. Lo aproximado
aquí es sustituir el volumen conductor por su trayectoria central y regularizar
el núcleo. Esa representación no valida el campo dentro o inmediatamente junto
a la cinta. Estar en el hueco central de una bobina puede estar suficientemente
lejos del **conductor**, aunque no sea campo lejano respecto del tamaño del imán.

`compare_elmer.py` registra para cada punto su distancia mínima a los segmentos
de corriente, la distancia en radios de hilo, los tres componentes FEM y de
referencia y el error vectorial. Rechaza puntos a menos de diez radios de la
trayectoria por defecto. **Diez radios es un filtro de ensayo, no una cota
universal de error**. Además compara la referencia filamentaria sin núcleo con
la regularizada: esa diferencia mide sensibilidad a la regularización, no todos
los errores de sustituir la sección real por una línea. Para cinta rectangular
este auditor se niega a usar el radio circular equivalente como criterio de
separación. No extrapolar esta prueba al máximo sobre el superconductor.

## Evidencia y límites

Piloto de tres vueltas, 48.672 tetraedros originales de conductor:

- Aire máximo 0,30 m, padding 1,3 m: 64.006 tetraedros de aire, generación
  inicial en 5,8 s. Con el `.sif` histórico, magnitud FEM/BS en el centro ≈0,184.
- Mismo dominio y conductor, selección de cortes corregida y 100 A por circuito:
  magnitud FEM/BS central ≈0,951, error **vectorial** ≈5,7 %; aproximadamente
  7,9 % y 8,7 % en los otros dos puntos interiores de diagnóstico. En puntos
  más exteriores el error vectorial todavía llegó a ≈46 %: comparar solo
  magnitudes ocultaría ese error de dirección. No equivale a validación final.
- Prueba automatizada de dos conductores separados: conservación de volumen,
  número de tetraedros conductores, interfaces y grupos tras escribir/releer.
- Regresión de exportación tubular: IDs globalmente únicos y conteo completo.

Pendientes para producción: convergencia de tamaño y extensión del dominio,
control de calidad y corriente por circuito en el arreglo, sentido de corriente
respecto a la trayectoria de referencia, representación real de cinta/materiales,
validación cerca del conductor y del máximo de campo. Elmer ya dispone de una
vía funcional para el piloto; no se certifica aún la solución del Geom14 completo.

## Separando el efecto de malla y el de extensión del dominio (2026-09-09)

Con el mismo conductor (48.672 tetraedros) y `.sif` corregido, se corrieron
dos combinaciones adicionales a las ya documentadas arriba, variando un solo
parámetro de `mesh_exterior.py` a la vez:

| Caso | padding (m) | air-size (m) | tetraedros de aire | [4,0,0] | [4,0.15,0] | [4,0,0.3] | [4,0,0.8] | [4,1,0] | [5,0,0] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Referencia (arriba) | 1,3 | 0,30 | 64.006 | — | — | — | — | — | — |
| Referencia (arriba) | 1,3 | 0,15 | — | 0,043 | 0,052 | 0,023 | ~0,07–0,15 | ~0,07–0,15 | ~0,07–0,15 |
| Malla más fina | 1,3 | 0,10 | 334.942 | 0,015 | 0,035 | 0,048 | 0,124 | 0,092 | 0,140 |
| Dominio más grande | 2,0 | 0,15 | 253.783 | 0,014 | 0,032 | 0,038 | 0,115 | 0,039 | 0,182 |
| **Ambos combinados** | **2,0** | **0,10** | **734.303** | **0,013** | **0,020** | **0,021** | **0,056** | **0,058** | **0,046** |

(Errores son **vectoriales relativos** contra la referencia filamentaria, como
en la sección anterior; los tres puntos interiores de la referencia de 0,15 m
son los valores exactos ya reportados arriba, los otros tres de esa fila son
el rango 7–15 % mencionado sin desglosar por punto — no hay un JSON guardado
de esa corrida para extraerlos exactos.)

**Lectura honesta, ahora con una tendencia clara:** refinar la malla y
agrandar el dominio por separado mejoran los puntos centrales de forma
comparable, sin que uno domine claramente al otro. El punto más lejano
ensayado, `[5,0,0]` (~30 radios de hilo), parecía **no mejorar con ningún
ajuste individual** — incluso empeoró con el dominio más grande solo
(0,182) — lo que en un primer momento se leyó como un límite no resoluble
con estos dos parámetros. **Combinar ambos ejes a la vez lo corrigió**:
0,046, la mejor cifra de las cuatro corridas para ese punto, y de hecho la
mejora en TODOS los puntos al combinar ambos ejes es mayor que la de
cualquiera de los dos por separado — el efecto es aproximadamente aditivo,
no hay evidencia de un límite de fondo no resoluble por malla/dominio en el
rango probado. La lectura anterior (que atribuía el estancamiento de
`[5,0,0]` a "algo más" — condición de frontera, corte de bobina, etc.) era
prematura: bastaba con refinar ambos ejes a la vez, no se había probado esa
combinación todavía.

Inspección de componentes que motivó la duda inicial: en `[5,0,0]` el campo
de referencia tiene una componente X casi nula por simetría del devanado
(∼4×10⁻⁸ T); con dominio más grande solo, el FEM daba ∼4×10⁻⁶ T en esa
misma componente (dos órdenes de magnitud mayor, aunque pequeña frente a
Y/Z) — esa componente espuria resultó ser sensible a malla insuficiente
más que a un problema de fondo, coherente con que desaparece al refinar
ambos ejes juntos.

**Qué sí se puede afirmar:** con `padding=2,0 m` y `air-size=0,10 m`
(734.303 tetraedros de aire, ~90 s de `ElmerSolver` en esta máquina), el
error vectorial en los 6 puntos de diagnóstico queda entre 1,3 % y 5,8 % —
una mejora sustancial y consistente sobre cualquier combinación individual
probada antes. Sigue sin ser una convergencia formal (solo 2 niveles de
refinamiento por eje, no una secuencia de Richardson ni un tercer nivel que
confirme que el error sigue bajando monótonamente) ni cubre el máximo de
campo sobre el conductor ni geometrías con más vueltas/curvatura — pero es
la configuración recomendada para repetir este piloto o extenderlo a un
arreglo mayor, en vez de cualquiera de las configuraciones anteriores.

## Barrido 3×3 de convergencia y nueva configuración recomendada (2026-09-10)

Extensión directa del barrido anterior: la misma matriz padding×air-size,
ahora con `padding ∈ {2,0, 3,0, 4,0} m` y `air-size ∈ {0,10, 0,07, 0,05} m`
(9 combinaciones), mismo conductor de tres vueltas y mismo `.sif` corregido.
El caso `padding=2,0 / air-size=0,10` es el ya documentado arriba (734.303
tetraedros de aire); se reutiliza como punto de control, no se repite.

| padding (m) | air-size (m) | tetraedros de aire | [4,0,0] | [4,0.15,0] | [4,0,0.3] | [4,0,0.8] | [4,1,0] | [5,0,0] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2,0 | 0,10 | 734.303 | 2,09 % | 1,89 % | 1,85 % | 2,74 % | 2,05 % | 9,05 % |
| 2,0 | 0,07 | — | 0,97 % | 0,97 % | 1,06 % | 6,00 % | 4,38 % | 5,85 % |
| 2,0 | 0,05 | 5.496.760 | 0,89 % | 1,10 % | 1,77 % | 5,55 % | 2,56 % | 7,84 % |
| 3,0 | 0,10 | — | 0,67 % | 0,97 % | 1,91 % | 3,40 % | 3,04 % | 5,51 % |
| **3,0** | **0,07** | — | **0,27 %** | **1,43 %** | **0,94 %** | **2,26 %** | **3,46 %** | **2,32 %** |
| 3,0 | 0,05 | 13.682.373 | **no completó** (ver abajo) | | | | | |
| 4,0 | 0,10 | — | 1,27 % | 4,11 % | 1,99 % | 4,84 % | 3,06 % | 5,58 % |
| 4,0 | 0,07 | 10.106.195 | **no completó** (ver abajo) | | | | | |
| 4,0 | 0,05 | 28.095.569 | **no completó** (ver abajo) | | | | | |

(Errores vectoriales relativos contra la referencia filamentaria, igual
convención que la sección anterior. Recorrido en una VM de 14 vCPU / 15 GiB
RAM / 12 GiB swap; conteos de tetraedros de aire omitidos con "—" cuando no
se guardó el manifiesto de esa corrida puntual.)

**Nueva configuración recomendada: `padding=3,0 m`, `air-size=0,07 m`.**
Es el mejor resultado de las 6 combinaciones que sí completaron — el más
bajo en 4 de los 6 puntos de diagnóstico, y el punto más lejano `[5,0,0]`
baja a 2,32 %, mejor que el 4,6 % de la configuración anterior. Reemplaza a
`padding=2,0 / air-size=0,10` como referencia de este documento.

**Patrón de retornos decrecientes:** de padding 2→3 hay mejora clara y
consistente; de padding 3→4 ya no la hay (`4,0/0,10` es peor que `3,0/0,10`
en 4 de 6 puntos) — el dominio ya está en régimen asintótico alrededor de
padding≈3 m, y seguir agrandándolo sin refinar la malla en la misma
proporción no ayuda más. Esto es consistente con la sección anterior
("el efecto es aproximadamente aditivo"): pasado cierto punto, agrandar
solo un eje dejó de traducirse en menor error.

**Tres combinaciones no completaron, por límite real de memoria de esta
VM, no por un problema del método:**
- `padding=3,0 / air-size=0,05` (13.682.373 tetraedros de aire): el proceso
  `ElmerSolver` fue terminado por el OOM killer del kernel (`SIGKILL`,
  código de salida 137) tanto con 14 hilos como reintentando con 4 hilos —
  descarta que el problema fuera solo de picos de memoria por hilos de
  OpenMP; es el tamaño absoluto de la malla en RAM+swap combinados (26 GiB
  en esta VM) lo que no alcanza.
- `padding=4,0 / air-size=0,07` (10.106.195 tetraedros de aire): terminó
  por `timeout` (1800 s) en el primer intento — sobrevivió a la memoria
  pero el ensamblaje se volvió demasiado lento, probablemente por
  paginación a swap durante el cómputo, no por falta de núcleos.
- `padding=4,0 / air-size=0,05` (28.095.569 tetraedros de aire, la
  combinación más pesada del grid): el propio `mesh_exterior.py` fue
  terminado por el OOM killer **durante la escritura del `.msh`**, antes
  siquiera de llegar a `ElmerSolver` — con 28 millones de tetraedros el
  paso de mallado en sí ya no cabe en esta máquina.

Ninguno de estos tres casos se recuperó reintentando con menos hilos
(`OMP_NUM_THREADS=4`): el cuello de botella es memoria total disponible,
no paralelismo — una máquina con más RAM podría completarlos sin cambiar
ningún parámetro del método. No se investigó bajar `--threads` en el propio
`mesh_exterior.py` (que sigue usando 14 para el mallado con Gmsh,
independiente de los hilos de `ElmerSolver`) como mitigación adicional.

No es una convergencia formal ampliada (siguen siendo 2-3 niveles por eje,
no una secuencia de Richardson), y sigue limitada al piloto de tres vueltas,
sección circular, un solo circuito — las mismas limitaciones ya señaladas
arriba. Pero con 6 puntos de este barrido más amplio, la lectura de
`padding=3,0/air-size=0,07` como mejor configuración conocida es más sólida
que la anterior (más combinaciones descartadas explícitamente, no solo
mejor resultado puntual).

## Búsqueda de configuraciones de bobina alternativas 100 % reproducibles (2026-09-10)

Motivación: Geom14/ARSSEM (ver `GEOM14_STATUS.md`) tiene vacíos de datos
documentados — separación entre bobinas del Double Helix, si el arreglo
lleva endcaps, corriente de operación vinculada específicamente a Geom14,
detalle capa-por-capa de la cinta YBCO. Se investigó si existe en la
literatura pública una configuración de bobina(s) para blindaje magnético
activo espacial que esté completamente especificada (sin vacíos que exijan
extrapolar), evitando así ese problema en la raíz.

**Resultado: ninguna fuente es plug-and-play, pero CREW HaT (corregido
2026-09-10, ver nota abajo) es un candidato genuinamente mejor que Geom14.**
El research inicial (búsqueda automatizada, sin acceso al PDF completo de
CREW HaT) subestimó esa fuente; una segunda verificación dirigida, que sí
descargó y leyó el reporte NIAC completo y la tesis de 2024, corrige esa
lectura — ver el bloque de CREW HaT más abajo. El patrón de omisión de
corriente de operación y número de vueltas que ya tiene Geom14 se repite,
con distinto grado, en el resto de la literatura de blindaje magnético
espacial revisada:

- **Ambroglini/Battiston et al.** (*Frontiers in Oncology* 6:97, 2016;
  PMC4896949, acceso abierto), el origen conceptual del propio diseño
  Double Helix que adoptó ARSSEM: especifica diámetro (2 m), ancho de cinta
  YBCO (4 mm) y campo integral objetivo (BL≈4 Tm), pero no publica
  corriente, número de vueltas, paso de devanado ni longitud exacta — el
  mismo vacío que Geom14, en la fuente de la que Geom14 deriva.
- **SR2S** (proyecto FP7, toroidal MgB2 de 120 bobinas racetrack): sí
  detalla composición de cable por capa y estructura de soporte, pero
  tampoco publica corriente/vueltas por bobina. Es la única de esta lista
  con un **demostrador físico real** construido y probado en corriente de
  transporte (CERN/Columbus Superconductors) — pero los valores medidos de
  corriente/campo de esa bobina de prueba no se pudieron confirmar desde
  fuentes de acceso abierto (quedan en papers con paywall de IEEE/ScienceDirect).
- **CREW HaT** (arXiv:2209.13624 es el preprint conceptual anterior, ICES
  2022, Desiati & D'Onghia; el documento con datos reales es el **reporte
  técnico NASA NIAC Phase I** — "Cosmic Radiation Extended Warding using
  the Halbach Torus", D'Onghia, Univ. Wisconsin-Madison, NTRS 20250002403,
  PDF completo de 80 páginas — más la **tesis de maestría de 2024**, Ziyang
  Hang, "Superconducting Magnets Design for Shielding from Cosmic Rays",
  asesor Franklin Miller, repositorio MINDS@UW handle 1793/85233).
  **Verificado leyendo ambos documentos completos (2026-09-10), no solo el
  abstract**: Halbach Torus de **8 bobinas elípticas**, radio Halbach 8 m,
  semieje mayor 4 m, aspect ratio 2 (semieje menor 2 m), campo pico ~10 T
  sobre el conductor, temperatura de diseño 40 K (Tabla 3.1, p. 15, y
  §4.5 del reporte NIAC). **Con una ambigüedad real, no resuelta por el
  propio reporte:** el dato de corriente de la Tabla 3.1 (`I = 1×10⁷ A`) es
  la corriente **total** del sistema de bobina, no la corriente de
  conductor ni un número de vueltas — el reporte deja abiertas dos
  alternativas de conductor sin decidir entre ellas: cinta YBCO de 4 mm
  (necesitaría ~125.000 vueltas para llegar a esa corriente total, con
  Ic real de conductor ~80 A a 10 T/40 K) o cable CORC de 8 mm (~2.632
  vueltas). La tesis de 2024 sí añade vueltas/capas concretas, grosor de
  winding pack y análisis de esfuerzo mecánico (hoop stress) para ambas
  opciones, pero sin cerrar cuál de las dos es la de diseño final. En
  síntesis: **más completo que Geom14** (dimensiones de conjunto, campo
  pico y temperatura sí están fijados sin ambigüedad, y hay curva Ic
  vs. campo/temperatura del conductor) pero **no elimina la necesidad de
  una decisión propia del equipo** — aquí, elegir conductor (cinta vs.
  CORC) en vez de estimar separación radial o presencia de endcaps como en
  Geom14. Es el candidato más prometedor de esta lista para adaptar al
  pipeline (Halbach de bobinas elípticas con corriente prescrita, sin
  quench ni transitorios, igual que el resto del pipeline ya asume).
- **NASA NIAC/MAARSS** (NTRS 20190002579, Advanced Magnet Lab): da
  geometría de conjunto (solenoides de 8 m ⌀ × 20 m, campo uniforme 1 T) y
  estructura de soporte, pero no corriente ni vueltas en el resumen
  disponible. El reporte completo (no solo el resumen NTRS) no se pudo
  decodificar con las herramientas de búsqueda usadas — queda como
  candidato a revisar manualmente, no descartado con certeza.
- **Double-Helix dipole original** (Goodzeit/Ball/Meinke, IEEE Trans. Appl.
  Supercond. 2003; reporte técnico OSTI 817768): un dipolo de acelerador
  real, construido y medido (4 T en apertura de 80 mm) — es el origen
  técnico del principio Double Helix, con datos de un magneto realmente
  fabricado, pero es geometría de acelerador de partículas (apertura de
  80 mm), no blindaje espacial, y a otra escala por completo que Geom14. El
  reporte técnico completo de OSTI tampoco se pudo decodificar con las
  herramientas de búsqueda; mismo caso que MAARSS, candidato pendiente de
  revisión manual.

**Conclusión práctica (corregida 2026-09-10):** ningún diseño publicado es
reproducible sin al menos una decisión propia del equipo, pero **CREW HaT
(reporte NIAC + tesis 2024 combinados) es un candidato genuinamente más
completo que Geom14/ARSSEM** y vale la pena evaluarlo como alternativa, no
solo como antecedente bibliográfico: fija dimensiones de conjunto, número
de bobinas, campo pico y temperatura sin ambigüedad, y da curva Ic del
conductor vs. campo/temperatura — la única decisión pendiente es elegir
entre sus dos alternativas de conductor (cinta YBCO vs. cable CORC), cada
una con su propio número de vueltas ya calculado en la tesis. Esto es
menos trabajo de extrapolación que el que exige hoy Geom14 (que además de
elegir conductor requiere estimar separación radial entre bobinas y decidir
si hay endcaps, sin ningún dato del paper para apoyar esa decisión). Si el
equipo decide migrar de Geom14 a CREW HaT como geometría de referencia, es
un cambio de alcance que debe decidirse explícitamente, no algo que este
documento resuelve por su cuenta — pero la comparación ya no favorece
seguir con Geom14 solo por default. Los otros candidatos (SR2S,
Ambroglini/Battiston, Double-Helix dipole de acelerador) siguen sirviendo
como antecedentes conceptuales o casos de validación de método, no como
reemplazo de la geometría de referencia. Dos reportes (OSTI 817768 del
dipolo Double-Helix, y el MAARSS completo de NTRS) siguen sin decodificarse
con las herramientas de búsqueda usadas — candidatos a revisión manual
futura, sin la prioridad de CREW HaT tras esta verificación.
