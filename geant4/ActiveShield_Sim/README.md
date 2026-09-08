# ActiveShield_Sim

Simulación Geant4 para estudiar blindaje magnético espacial con fantoma
ICRP110 y dosis por órgano. Base: ejemplo oficial `ICRP110_HumanPhantoms`,
conservado en `README_ICRP110_original.md`; datos descargados durante CMake.

## Estado actual y decisiones (2026-09-08)

- Geometría del hábitat: cilindro cerrado, diámetro exterior **5.6 m**, largo
  exterior **10 m**, eje Z. Casco de **G4_Al, 1.5 cm**, tapas planas del mismo
  espesor. Es una referencia radiológica, no un diseño estructural de vuelo.
- Exterior **G4_Galactic** (vacío); aire del hábitat y materiales ICRP110
  conservados. Fantoma masculino o femenino centrado, posición fija.
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

`male.in` y `female.in` mantienen el scorer original por órgano. El haz de
`primary.mac` ahora nace en **(-6, 0, 0) m**, en el exterior, y apunta hacia
+X con protones de 250 MeV. Antes nacía a -27 cm, dentro de la cabina: las
corridas anteriores no probaban el cruce del casco por el primario.
Son pruebas de funcionamiento; sus 1000 eventos no fijan el presupuesto
estadístico de producción ni representan 1000 corridas independientes.

## Configuración antes de /run/initialize

```text
/spacecraft/hullThickness 1.5 cm
/spacecraft/worldHalfSize 10 m
/spacecraft/coilGeometry /ruta/absoluta/componentes.gdml
/spacecraft/fieldMap /ruta/absoluta/geom14.map
/spacecraft/fieldScale 1
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

## Qué se reutiliza de GCR_SEP_Sim

Se reutilizan las ideas de manifiesto, semillas, reanudación y agregación;
**no basta `run_sweep.py --build-dir ...`**. Ese script ejecuta `gcrsim`, usa
`/detector/...` y `/gun/model`, y espera una fila de dosis por corrida.
Aquí el ejecutable es `ICRP110phantoms`, la fuente es `/gps/...` y el scorer
es por órgano. El nuevo esquema necesitará especie × energía × configuración
× repetición, además de un identificador del mapa y de los materiales.

`QGSP_BIC_HP` sigue siendo la physics list de este proyecto; `Shielding` es
la del piloto. Elegir y documentar una lista para los resultados definitivos.
Los espectros SPENVIS se usarán como **pesos posteriores** de la respuesta por
bin; no es necesario portar `SpectrumSampler` para elegir energías al azar.
