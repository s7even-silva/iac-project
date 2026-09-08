# Verificación del dominio y ruta hacia Geom14

## Estado y alcance

El piloto `examples/dh_pilot.json` define **un circuito Double Helix cerrado**,
con dos hélices concéntricas de inclinaciones opuestas y retornos suavizados.
La corriente recorre las hélices en sentidos opuestos. El CAD y la poligonal
de corriente se obtienen de la misma spline periódica de OpenCASCADE.
Su parametrización antes del suavizado es
`x=r cos(t), y=r sin(t), z=p(t/(2π)-N/2) ± r cot(α) sin(t)`.
Los retornos son parte del circuito; no se suman hélices abiertas aisladas.

**Todos los números del JSON son parámetros de ensayo elegidos para desarrollar
el código, no valores extraídos de ARSSEM ni aprobados para fabricación.**
El sólido es un conductor circular de cobre de referencia. No representa cinta
YBCO, aislamiento, estructura ni crióstato. Cambiar parámetros puede crear
autointersecciones: completar mallado, comparación de masas y chequeos Geant4
para cada configuración. La spline suaviza las uniones y modifica localmente
la hélice analítica; se debe revisar ese diseño de retorno antes de producción.

En [ARSSEM, §4.3 y §5.1, figuras 5.3–5.4](https://arxiv.org/pdf/1209.1907),
Geom14 mejora especialmente la composición material de cinta YBCO respecto
a Geom13. Reproducir solo la forma DH no reproduce Geom14. Próximos hitos:

1. Fijar con trazabilidad dimensiones, disposición barrel/endcaps, vueltas,
   corriente y estructura; distinguir parámetros publicados de decisiones del equipo.
2. Sustituir el cobre de ensayo por entidades/materiales de devanado, soporte,
   aislamiento y crióstato; validar masa y espesor areal por dirección.
3. Preparar Elmer: dominio de vacío, grupos de corriente, solver y condiciones
   de contorno; fijar versiones y convergencia FEM. No hay ejecución Elmer aún.
4. Validar campo exterior contra Biot–Savart, exportación/interpolación y tracking;
   después estudiar respuestas por bin y dosis ponderadas.

`compute_field.py` integra analíticamente cada segmento recto de la poligonal,
con el núcleo regularizado `(|r-r'|²+a²)^(-3/2)`, donde `a` es el radio del
conductor. Evita singularidades en la grilla, pero **no equivale a resolver la
distribución de corriente en una sección finita ni el estado superconductor**.
Sirve como referencia exterior cuando la distancia al hilo es mucho mayor que
`a`; cerca/dentro del conductor se necesita FEM con J volumétrica u otra solución
validada. La corriente del ejemplo es 100 A, no un ajuste a 2 T.
No utilizar este mapa ni su grilla gruesa para resultados radiológicos oficiales.

## Propuesta operativa 2A, 4A, 8A

`A` es un radio, respecto al origen común, que encierra **todo el ensamblaje**
magnético. El planificador obtiene una cota conservadora de la caja CAD del
archivo de corriente; con varias bobinas hay que aportar la caja del ensamblaje
o un `--enclosing-radius` que lo encierre. No usar el radio de una sola espira.
También debe quedar cubierto el hábitat.

Se propone ensayar `R=2A,4A,8A`. Con A=10 m: 20, 40, 80 m.
**Esta secuencia es una propuesta del proyecto, no una norma ni una distancia
recomendada por ARSSEM.** El lector actual usa cubos: R es el **semilado** del
mapa y el radio de su esfera inscrita; los vértices alcanzan √3 R. No afirmar que
este ensayo corta el campo esféricamente a R. Fuera del mapa Geant4 aplica B=0.

El planificador escribe `domain_plan.json`, comandos `generate_maps.sh` y macros
PreInit que fijan el mismo World para los tres casos. No ejecuta simulaciones,
no configura la fuente y no certifica convergencia. El límite predeterminado de
un millón de nodos evita asignaciones accidentales; revisar costes antes de
autorizar un `--max-points` mayor en los comandos generados.
Los tamaños de almacenamiento son estimaciones (solo B binario y texto);
el RSS real incluye otras estructuras. Una grilla regular crece como R³/h³.

Durante las simulaciones oficiales:

1. Conservar geometría, materiales, corriente, bins, resolución local y tolerancias
   de tracking. Refinar primero la discretización del campo; ampliar R no la valida.
2. Usar una misma fuente exterior para comparar los tres recortes: el plan propone
   esfera de radio 8A y World de semilado ≥8A+1 m. Falta configurar el generador
   de producción con muestreo isotrópico entrante y normalización coherente.
   Validar **por separado** que alejar la fuente aún más no cambia la respuesta;
   8A no es automáticamente el infinito físico.
3. Registrar por especie/bin/órgano la respuesta, incertidumbre, semillas,
   transmisión y cambios de trayectoria, además de dosis reponderada. Comparar
   2A→4A y 4A→8A; ampliar si no convergen. Para órganos con respuesta casi nula
   usar también un umbral absoluto, no cocientes inestables.
4. Propuesta de presupuesto: error sistemático de dominio <1% en observables
   relevantes, con incertidumbre de la **diferencia** suficientemente pequeña.
   Si se reutilizan historias/semillas, estimar covarianza o diferencias por
   bloques; no asumir muestras independientes. Que dos resultados sean compatibles
   con ruido grande no demuestra convergencia al 1%.

La grilla ajusta ligeramente h para alcanzar exactamente ambas caras; el paso
real queda en el manifiesto. Ese pequeño cambio también debe controlarse en una
comparación precisa (elegir R/h entero, o repetir con refinamiento adicional).

## Comprobaciones con antecedentes, superiores a elegir una distancia fija

Para el **dominio FEM**, estudiar ampliaciones conservando la malla próxima al
imán y comparar campos e integrales en una región de interés fija. COMSOL muestra
la convergencia al ampliar el dominio con condiciones exteriores diferentes,
y el uso de elementos infinitos como alternativa:
[estudio de condiciones de contorno para bobinas](https://www.comsol.com/blogs/how-to-choose-between-boundary-conditions-for-coil-modeling).
Su promedio de condiciones de contorno funciona en el ejemplo presentado;
no es una garantía matemática para nuestro ensamblaje 3D. Tampoco se ha
verificado aquí una implementación equivalente de elementos infinitos en Elmer.

Para corrientes prescritas en medios con μr≈1, Biot–Savart proporciona una
referencia de espacio libre sin frontera FEM artificial. Recomiendo combinar
esa comparación independiente **lejos del conductor** con convergencia de dominio
y malla. El ensayo de espira circular del repositorio contrasta la solución axial
analítica; fundamento en
[OpenStax, campo de una espira](https://openstax.org/books/university-physics-volume-2/pages/12-4-magnetic-field-of-a-current-loop).
Refinar segmentos y reducir el efecto del núcleo antes de atribuir discrepancias
a Elmer. No extrapolar esa verificación exterior al interior del devanado.

Para el **recorte del mapa de transporte**, añadir el diagnóstico
`δθ ≈ ∫ B_perp ds / (Bρ)` a lo largo de trayectorias exteriores, con rigidez
`Bρ=p/|q|` en unidades SI. Es una estimación de pequeña deflexión; evaluar la
especie y energía de menor rigidez relevante y también desplazamientos/aceptación.
Un máximo de B pequeño en la frontera no basta: importa la integral omitida.
El decaimiento dipolar lejano ~r⁻³ ayuda a estimar colas, pero verificar que ya
se está en ese régimen y no usarlo cerca del ensamblaje. La aceptación final
sigue siendo la estabilidad de observables de transporte y dosis.

## Refinamiento con distancia

Para FEM, usar tamaños condicionados por distancia a superficies del conductor,
curvatura y variación de B/J, con transición gradual. El
[tutorial t10 de Gmsh](https://gmsh.info/doc/texinfo/gmsh.html#t10) documenta
`Distance` + `Threshold` (`SizeMin/Max`, `DistMin/Max`); **no prescribe una distancia
fina universal**. Determinarla comparando soluciones refinadas en puntos comunes
y mediante un estimador de error del solver, cuando esté disponible.

La malla actual del conductor solo prepara CAD/GDML y es aproximadamente uniforme.
Todavía no genera la malla exterior FEM graduada. El mapa que importa Geant4
también sigue siendo uniforme: cambiar Gmsh a malla graduada no cambia ese contrato.
Para dominios muy grandes convendrá implementar mapas por bloques/niveles o un
campo exterior analítico validado y continuo en la unión; eso queda pendiente.
