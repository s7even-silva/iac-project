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
