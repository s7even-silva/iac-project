# Ficha del imán: referencia ARSSEM frente a implementación

Actualizado 2026-09-08. **Geom14 es la base de referencia elegida, no una
geometría completa ya implementada ni una ficha constructiva cerrada.**
El JSON `examples/dh_pilot.json` se identifica expresamente como
`computational_pilot_not_geom14`. El generador solo admite ese estado.

## Cambiar el physics list de ActiveShield_Sim (Shielding vs. QGSP_BIC_HP)

Mecánicamente es un cambio de pocas líneas en `ICRP110phantoms.cc`: reemplazar
`#include "QGSP_BIC_HP.hh"` + `new QGSP_BIC_HP()` por `G4PhysListFactory` +
`GetReferencePhysList("Shielding")`, igual que ya hace `GCR_SEP_Sim/main.cc`.
Ambas son `G4VModularPhysicsList`, así que el resto del código no cambia.

Un detalle que sí hay que replicar si se hace este cambio (o si se agrega
campo magnético confinante con cualquier lista): `GCR_SEP_Sim` registra
además `G4StepLimiterPhysics()` para que `SetUserMaxTrackLength()` funcione
y evite partículas atrapadas girando en el campo (ver nota técnica en
`AGENTS.md`) — no es específico de `Shielding`, hace falta con cualquier
lista si el campo puede confinar partículas indefinidamente.

**Ventajas/desventajas:** `Shielding` está diseñada específicamente para
problemas de blindaje de radiación (la recomendación oficial de Geant4 para
este tipo de estudio) y tiene buena cobertura de neutrones de baja energía,
pero es más cara computacionalmente. `QGSP_BIC_HP` (heredada del ejemplo
oficial de ICRP110) usa Binary Cascade, preciso en el rango de energías
típico de dosimetría médica/de fantomas — tiene precedente directo para
"dosis por órgano en un fantoma humano". Ninguna es objetivamente superior
para este caso; lo que sí importa (ya señalado en la sección de más abajo)
es que ambos proyectos comparen bajo la misma lista si sus resultados se van
a poner uno junto al otro — mezclar listas entre `GCR_SEP_Sim` y
`ActiveShield_Sim` invalidaría esa comparación aunque cada uno por separado
sea razonable. Decidir cuál usar en producción, con benchmarks reales, sigue
pendiente y no bloquea el trabajo de geometría del imán.

## Referencias publicadas y pendientes

Fuente: [ARSSEM](https://arxiv.org/pdf/1209.1907), §4.3, §5.1 y §6.
No mezclar el diseño electromecánico conceptual con las simplificaciones
de las configuraciones de transporte radiológico:

| Magnitud | Referencia publicada | Lo que todavía falta cerrar para nuestro arreglo |
|---|---|---|
| Topología | Concepto DH de 12 bobinas laterales (§4.3); barrel/endcaps en la familia Geom13/14 (§5.1) | Coordenadas, orientación, conexiones y disposición exacta de los extremos |
| Diámetro | DH de 2 m (§4.3); 2,04/1,35 m para barrel/endcaps Geom13 (fig. 5.4) | Distinguir diámetro útil, devanado y envolvente; elegir las dimensiones que se reproducirán |
| Longitud | Concepto de 18 m con meseta de campo de 10 m (§4.3) | Extremos y separación del casco; no sustituir 18 m por 10 m silenciosamente |
| Devanado | Estudio de ocho capas de cinta (§4.3) | Vueltas, paso, inclinación, conexiones serie/paralelo y sentido de cada capa |
| Conductor | YBCO 2G; referencia conceptual de 50 mm × 0,2 mm, película de 2 µm (§4.3) | Conductor concreto, composición completa, fracciones másicas y aislamiento |
| Operación | Estimación Ic≈10 kA a 25 K y 2,5–3 T paralelos a la cinta (§4.3) | Corriente de operación, curva Ic local, deformación y margen; Ic no es Iop |
| Protección | Estudio Geom14 con 2/4/8 T y 4/8/16 T·m (tabla 5.4) | Elegir caso de referencia y trayectorias/región de evaluación |
| Estructura | Conceptos de soporte Al, aislamiento multicapa y criogenia (§6) | Materiales, espesores, contactos y masas de nuestro modelo radiológico |

Geom14 mejora la composición YBCO respecto a Geom13. El informe no equivale a
tener en el repositorio su CAD/CoilCad, todas las coordenadas, la ley de corriente
y la composición lista para importar. Hay además una inconsistencia de unidades
en §4.3: ocho espesores de 0,2 mm suman **1,6 mm**, no 1,6 µm; no adoptar ese
valor textual como espesor sin resolver qué apilamiento describe.

## Valores que sí ejecuta el código hoy

| Parámetro del piloto | Valor |
|---|---|
| Circuitos y hélices | Un circuito cerrado, dos hélices concéntricas y retornos suavizados |
| Centro / eje | (4,0,0) m / Z |
| Radios de trayectoria | 0,35 y 0,65 m |
| Vueltas | 3 por hélice |
| Paso / inclinación | 0,30 m/vuelta / ±45° antes del suavizado |
| Avance axial del término de paso | 0,90 m; la extensión total también incluye inclinación y retornos |
| Sección / material | Circular, radio 0,012 m; cobre elemental, 8960 kg/m³ |
| Corriente | 100 A en todo el circuito, recorrido contrario en las dos hélices |
| Temperatura, Ic, crióstato, soporte, aislamiento | No modelados |
| Solver del campo | Biot–Savart regularizado en Python/NumPy; **Elmer no está configurado ni se ejecuta** |

Estos son valores de desarrollo, no una reducción a escala validada de Geom14.
Replicar esta bobina doce veces no bastaría para reproducirlo. La operación inicial
seguirá siendo magnetostática con corrientes prescritas; corrientes de apantallamiento,
transitorios y quench permanecen fuera del alcance implementado.

## Qué significa campo de protección

Es el campo exterior que atraviesan las partículas antes de llegar al hábitat.
Evaluar su distribución y `∫B_perp ds` en trayectorias representativas, además de
la respuesta radiológica. Propongo **el caso de referencia de 2 T / 4 T·m** como
primer objetivo de comparación con ARSSEM; todavía no se ha dimensionado un
devanado que lo produzca. No significa 2 T uniformes en la cabina ni en todo World.

Se deben informar por separado:

- Campo útil y uniformidad en una región explícita de protección.
- Máximo sobre el conductor, con componentes paralela/perpendicular a la cinta.
- Máximo residual en toda la cabina, con un límite de diseño aún por acordar.

El auditor actual solo informa **dos sondas puntuales**: centro de la bobina y
origen de la cabina. Para el piloto, sus módulos son aproximadamente 0,384 mT
y 0,931 µT, respectivamente. No son máximos ni demuestran protección efectiva.
El núcleo regularizado impide utilizar ese cálculo como campo exacto dentro
del conductor; el máximo del devanado queda explícitamente `null`.

## Consistencia numérica y corriente crítica

Sí, hay que comprobarla antes del arreglo completo. Conviene distinguir `ℓc`
(longitud de conductor, metros) de `Ic` (corriente crítica, amperios):

- `N I` da amperio-vueltas. En el piloto son **300 A·vueltas por hélice**;
  no se suman como escalares dos hélices recorridas en sentido contrario.
- La longitud total medida de la trayectoria es **23,6559 m**, incluidos los
  retornos y todas las vueltas. No volver a multiplicarla por N. `I ℓc` tiene
  unidades A·m; tampoco determina por sí solo B, que depende de toda la geometría.
- Comprobar `∫J·n dS = I` en secciones, continuidad `∇·J=0`, cierre de retornos,
  suma de corrientes en conexiones y asignación de corriente por cinta/cable.
- Con conductor elegido, evaluar `Ic(B,T,θ,ε)` en el devanado y la fracción
  `Iop/Ic`; el margen de corriente es `1-Iop/Ic`. Fijar el margen requerido
  y resolver el campo propio de forma consistente. No usar Ic a 77 K/campo
  propio como si fuera Ic a otra temperatura y campo aplicado.
- Comprobar longitud, sección, masa `ρV`, espesor areal y empaquetamiento; después
  convergencia de FEM, exportación, interpolación, dominio y tracking.

La [ficha de SuperPower](https://www.superpower-inc.com/specification.aspx)
ilustra por qué hay que elegir una cinta concreta: distingue sustrato,
estabilización, aislamiento y dependencia de Ic con temperatura/campo. No se ha
adoptado un producto de ese fabricante ni equiparado con el supuesto de ARSSEM.

Nueva herramienta:

```bash
field/.venv/bin/python field/audit_dh.py \
  field/generated/dh/current_path.json field/generated/dh/audit.json \
  --mesh field/generated/dh/dh.msh
```

La malla debe corresponder al mismo CAD y contener solo el conductor, en metros.
Calcula longitud, NI, masa CAD, volumen de tetraedros, diferencias y sondas de B.
El argumento opcional `--critical-current` solo calcula un cociente con un Ic
aportado por el usuario: **no selecciona una curva ni valida superconductividad**.
Sin Ic, margen y cociente quedan `null`; `production_validated` siempre es `false`.
El auditor no sustituye los chequeos topológicos del conversor ni solapamientos.

## Materiales y criogenia

El GDML DH actual contiene únicamente cobre; **no incluye crióstato**. El soporte
Al del viejo ejemplo del anillo tampoco es soporte del DH. Para el modelo real,
representar por separado el conductor compuesto, aislamiento, soporte y envolvente
térmica, con masas justificadas. No modelar toda una cinta como YBCO puro.
El concepto criogénico del informe no se traduce automáticamente en un recipiente
convencional alrededor de cada bobina: hay que escoger qué envolventes, MLI,
refrigerante y equipos entran en la geometría y justificar exclusiones.

## Physics list y blindaje pasivo

`GCR_SEP_Sim` sigue usando **Shielding**. `ActiveShield_Sim` usa **QGSP_BIC_HP**.
Añadir bobinas o campo no exige cambiar ninguna de las dos. Ambas deben evaluarse
para las especies, energías y secundarios del estudio; mantener la misma lista
en todos los escenarios de una comparación. Para producción, comparar respuestas
por bin con listas candidatas, datos/benchmarks y modelos de iones; el nombre
Shielding no garantiza por sí solo menor incertidumbre.
Fuentes oficiales: [Shielding](https://geant4.web.cern.ch/documentation/dev/plg_html/PhysicsListGuide/reference_PL/Shielding.html)
y [QGSP_BIC](https://geant4.web.cern.ch/documentation/dev/plg_html/PhysicsListGuide/reference_PL/QGSP_BIC.html).
En este cambio **no se cambia la lista física**.

Antes de este cambio solo existían la propuesta de escenarios en ActiveShield_Sim
y las capas legadas en GCR_SEP_Sim. Ahora ActiveShield_Sim dispone de un adaptador
PreInit, repetible, desde el casco hacia fuera, con espesores **en centímetros**:

```text
/spacecraft/addPassiveLayerCm G4_Al 1
/spacecraft/addPassiveLayerCm G4_POLYETHYLENE 2
```

Cada capa es una envolvente cilíndrica cerrada, con tapas planas; no reduce la
cabina ni reemplaza el casco. Las capas son hermanas bajo `MagnetEnvelope`.
Se imprimen masa y densidad areal normal; se rechazan materiales fuera de Al/PE,
espesores no positivos, falta de cobertura del dominio y solapamientos detectados.
No añadir comandos deja las capas desactivadas. Se puede combinar con GDML y
`fieldScale=0/1` para casos pasivo o híbrido. Si la capa invade una bobina,
corregir dimensiones; no se recorta automáticamente.
Los espesores del ejemplo son de prueba. Comparar también a masa o densidad
areal comparable, no solo a igual espesor. Falta el orquestador completo de
escenarios por bins; este adaptador resuelve la geometría, no ese análisis.

## Qué representa el 3,06% de diferencia

Se comparó el **volumen material de la bobina**, no el tamaño de World ni el
volumen de campo:

| Representación del mismo conductor piloto | Volumen (m³) | Masa Cu (kg) |
|---|---:|---:|
| CAD OpenCASCADE | 0,01070421 | 95,9097 |
| Malla lineal / GDML | 0,01037638 | 92,9723 |

`(Vmalla/VCAD - 1) ×100 = -3,0626%`: unos **2,94 kg de cobre menos**.
Los triángulos planos aproximan las superficies curvas. El conversor conserva
el volumen de los tetraedros al extraer su frontera; la pérdida procede del
mallado geométrico, no de omitir arbitrariamente tetraedros en GDML.

Puede afectar espesores atravesados, interacciones y secundarios. **No implica
3,06% de error en dosis**: esa relación no es lineal y hay que medir convergencia
radiológica. El mapa Biot–Savart usa la curva CAD, no esa malla, por lo que la
masa perdida tampoco equivale a una disminución automática de B.

Ahora el JSON expone `mesh_min_size_m`, `mesh_size_m` (máximo) y
`mesh_points_per_circle`. Reducir los dos tamaños y aumentar el refinamiento
por curvatura, regenerar y auditar volumen/masa; luego comprobar dosis. Aumentar
solo los puntos por círculo puede no surtir efecto si el tamaño mínimo lo impide.
Así lo especifica [Gmsh, tamaños de elemento](https://gmsh.info/doc/texinfo/gmsh.html#Specifying-mesh-element-sizes).
El presupuesto de aceptación de masa/dosis final sigue pendiente; 3,06% no se
ha aceptado como precisión de producción.
