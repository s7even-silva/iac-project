# Auditoría de bugs y requisitos para la próxima producción (2026-09-30)

> **Nota (2026-10-01, inicio de la v2):** los archivos de la v1 que este
> documento cita y ya no están en `main` (GCR_SEP_Sim, `useful-examples/`,
> `scripts/pilots/`, resultados del barrido de 600, `plan_estadistico.md`,
> scripts de siembra del coordinator, etc.) se conservan en el tag
> [`v1-archivo`](https://github.com/s7even-silva/iac-project/tree/v1-archivo).

Revisión completa de `ActiveShield_Sim` (C++ y Python), los pilotos
estadísticos, el coordinator y el worker. Se revisaron todos los archivos
que el proyecto modificó respecto del ejemplo oficial ICRP110
(`useful-examples/ICRP110_HumanPhantoms`, que está intacto). No se
revisaron en detalle `GCR_SEP_Sim` (piloto histórico), los scripts de
mallado de `field/` (salvo la exportación del mapa) ni los instaladores de
`infra/deploy/`.

Estado: **corregido** (código cambiado y verificado), **pendiente**
(necesita decisión de equipo o una corrida nueva) o **documentado**.

## A. Críticos: invalidan resultados ya generados

| # | Bug | Efecto | Estado |
|---|---|---|---|
| A1 | La malla de scoring estaba fija en el origen (`/score/mesh/translate/xyz 0 0 0`) mientras el fantoma se desplazaba. | Las 480 corridas con `offset_x_m ≥ 1` del barrido de 600 miden aire de cabina etiquetado como órganos (dosis ~1000 veces menor). | **Corregido** en `run_organ_sweep.py` y `pilots/pilot_common.py`. Verificado: sin campo, la dosis en x=1 m da 0.91 veces la de x=0. Hay que repetir esas corridas y actualizar los workers. |
| A2 | Todos los primarios apuntan al origen (`dir = -onSphere`), lo que es incompatible con el peso `π R² Φ`. | Las dosis absolutas están infladas, sobre todo en x=0 (colon GCR ≈ 2e-2 Gy/día, ~100 veces lo esperable), y dependen del radio de la esfera. Los pilotos de las Fases 7–10 también usaron apuntado radial. | **Opción agregada** (`/gun/angularDistribution cosine`). El default sigue en `radial` hasta que decida el equipo. Las conclusiones de la Fase 8 (épsilon de binning) deben revalidarse con ley coseno. |
| A3 | `aggregate_organ_doses.py`, vista por órgano: `R = Σ(dose_run·n)/Σn` es la dosis de una corrida, no por primario. | Los `resultados_organo_agregados_*.csv` versionados estaban inflados por un factor N (=10 000). Ejemplo: órgano 43 = 1967 Gy/día. Las vistas por categoría no estaban afectadas. | **Corregido** (`R = Σdose_run/Σn`). Con los mismos datos el órgano 43 da 0.197 Gy/día. Los CSV agregados viejos se eliminaron y `resultados/` se reorganizó (ver su README). Solo x=0 se reprocesó (`resultados/x0_reprocesado_2026-09-30/`), y sigue inflado por A2. |

## B. Altos: sesgan o pueden sesgar resultados futuros

| # | Bug | Estado |
|---|---|---|
| B1 | El agregador ignoraba `n_bins`: calculaba los pesos con la grilla de 8 aunque los datos fueran de 16 (pesos equivocados) o de más de 8 (`KeyError`). | **Corregido**: toma la grilla de los datos y rechaza mezclas de grillas. |
| B2 | Sin control de duplicados: una (corrida, repetición, órgano) en dos archivos sumaba su edep dos veces y N una sola vez, duplicando la dosis. El glob documentado `job_*/*/results.csv` incluye todos los intentos de un job. En los 323 resultados actuales no hay duplicados. | **Corregido**: el agregador aborta si encuentra un duplicado. |
| B3 | La vista Welch por bin nunca llenaba `bins_ausentes`, y la vista pooled omitía en silencio los bins sin datos (dosis incompleta sin aviso). | **Corregido**: los bins esperados salen de la grilla; los ausentes se reportan en el CSV y con una advertencia. |
| B4 | Esquema de semillas `BASE + 1000·rep + 2·index`: con 500 combinaciones o más, las semillas de la repetición r chocan con las de r+1. Ocurre con 3 casos × 64 bins o con 6 casos × 32 bins. | **Corregido** con una guarda que aborta. Ampliarlo requiere una versión nueva de semillas. |
| B5 | Los resultados no registran procedencia (commit, hash del binario, modo angular, versión de la plantilla). El coordinator no puede rechazar resultados de workers con código viejo (por ejemplo, con el bug A1). | **Pendiente**, requisito R9. Bloquea sembrar una producción nueva. |
| B6 | Límite de longitud de traza (3·2R ≈ 41.7 m en el vacío) sin contador: una partícula legítima que dé vueltas en el campo se corta sin registro. Puede haber un sesgo hacia abajo en bins de baja energía que no se puede medir. | **Pendiente**, requisito R6. |
| B7 | La esfera fuente corta el arreglo de bobinas y el mapa se trunca en sus caras (0.16–0.40 T) con frontera Elmer `AV=0`. | **Documentado** en `geant4/ActiveShield_Sim/docs/modelo_realista.md`. |
| B8 | `submit_result` v1 del coordinator no verificaba `fase` (v2 sí). | **Corregido** (tolera filas sin `fase`). |

## C. Medios: definición dosimétrica

| # | Problema | Estado |
|---|---|---|
| C1 | No se aplica w_T ni se calcula dosis efectiva. "Tejidos restantes" se pondera por masa: el músculo pesa 29.0 de 30.9 kg, así que domina; ICRP103 usa la media aritmética de 13 órganos por sexo. Incluye la tráquea, que no está en la lista de ICRP103. Mama incluye tejido adiposo (ICRP usa el glandular). Pulmón incluye la sangre pulmonar. | Pendiente (solo post-proceso). |
| C2 | w_R = 20 para todo He de GCR. A GeV/nucleón el LET es bajo (Q≈1), así que sobreestima. | Pendiente: Q(L), requisito R2. |
| C3 | Energía fija en la media geométrica de cada bin: introduce un error de discretización (el problema de la Fase 8). | Pendiente, ver R8: muestrear la energía dentro del bin elimina el sesgo. |
| C4 | Error estándar intra-run con S2 por voxel (Camino B): subestima (mediana 0.48), y el N del órgano es el número de pares voxel-evento. | Pendiente: R1 (Camino A). |
| C5 | Solo fantoma AM. Además, las plantillas tienen la malla de AM fija (254×127×222, 2.137 mm) y el agregador lee `AM_organs.dat`, `AM_spongiosa.dat` y las masas masculinas. Correr AF sin cambiar eso asignaría mal los voxels sin dar error. | Pendiente: R10. |
| C6 | La Fase 8 excluye el órgano 0 pero no el 140 (aire dentro del cuerpo) en el total. | Menor: el efecto es despreciable en un cociente. |
| C7 | El aire de cabina tiene 0.001 g/cm³ y N/O 80/20 (el real: 1.2e-3 con Ar). | Menor. |
| C8 | `ICRP110.out` tiene un nombre fijo: dos corridas en el mismo directorio de build se pisan. | Ya documentado; el worker usa un directorio propio. |

## Hallazgos posteriores (2026-10-04): geometría de las bobinas frente a NIAC

Revisión de `field/production/` contra el reporte NIAC Phase I (D'Onghia,
NTRS 20250002403; PDF en la máquina de desarrollo, fuera del repo). Las
páginas citadas son las del PDF.

| # | Hallazgo | Efecto | Estado |
|---|---|---|---|
| A4 | **La disposición simulada no es la de CREW HaT.** El arreglo de producción usa el patrón Halbach dipolar K=1 (θ_k = 2φ_k, `generate_ellipse_array.py`), elegido el 2026-09-10 porque las fuentes no fijaban el patrón. NIAC sí lo describe: «rotating magnetic polarities» que generan un campo alrededor del arreglo «while suppressing the magnetic field in the habitat region at the center» (§2, p. 8), un campo «weak or virtually non-existent in the crew habitat» (§2, p. 8); en la fig. 3.1(b) (p. 10) las cuatro bobinas cardinales están en planos radiales y las cuatro diagonales en planos tangenciales, y la fig. 3.9 (p. 16) muestra «four coils facing the axis of symmetry». K=1 hace lo contrario: un dipolo uniforme **dentro** de la nave (0.54 T en el eje con Elmer). | Todo lo que depende del campo: el mapa de producción, la preselección del radio de P1 (paso 1) y cualquier dosis con campo. Las dosis de la v1 ya eran inválidas por A1–A3. El criterio del ablation que respaldó a K=1 (uniformidad de \|B\| dentro de la nave, `CREWHAT_STATUS.md`) mide una propiedad que el diseño de NIAC busca suprimir, y no mide dosis. | **Pendiente.** Cambio de plan en `plan_piloto.md` (D9 y P1): producción con la disposición de NIAC y comparación con K=1 en P1. |
| B9 | **Las bobinas simuladas pesan unas 5 veces más que las de NIAC.** Cada bobina es un sólido de sección cuadrada de 0.67 × 0.67 m (supuesto propio, `CREWHAT_STATUS.md`) lleno de CORC homogeneizado a 8.96 g/cm³: 8.70 m³ y 77.9 t por bobina, 623 t el arreglo. NIAC da para la bobina elíptica CORC 40 vueltas por capa, 67 capas, 0.67 m de espesor radial y **15.6 t** por bobina (tabla de §4.10.2, p. 49). Con cable de 8 mm, 40 vueltas por capa dan unos 0.32 m de ancho, no 0.67 m. | Exceso de material en la geometría de transporte: más secundarios producidos en las bobinas, con un sesgo hacia más dosis que no se puede corregir después. El campo no cambia (la corriente total es la misma). | **Pendiente.** Candidato: sección de ~0.67 × 0.32 m con densidad efectiva ajustada a 15.6 t por bobina; se decide junto con A4, porque los dos regeneran el GDML. |

Chequeo exploratorio de A4 (Biot-Savart con filamentos, no es un piloto):
`field/studies/disposicion_bobinas_2026-10-04.py` y su salida `.txt`. Con
θ_k = 90° − φ_k, la única asignación de sentidos que respeta las
orientaciones de la fig. 3.1(b) con polaridad rotando de forma continua,
|B| es 0 en el centro y 0.013 T de media a 2 m del eje, frente a 0.52 y
0.55 T con K=1. Coincide con el «campo suprimido» de NIAC y con el centro
casi sin campo de su fig. 3.2 (p. 11). El reporte no dice el sentido de
la corriente de cada bobina, así que esa asignación queda como supuesto
propio declarado hasta confirmarla con la fig. 3.2 o con los autores.

Dos datos más del reporte para quien prepare la charla o el paper: el
radio de Halbach de diseño es 8 m (§3.1, p. 12; la fig. 3.1(b) dibuja un
anillo más chico, y las figs. 3.2 y 3.9 vienen de la ref. [35], un diseño
anterior con bobinas de pista de carreras), y no hay en
el reporte una cifra de 24 t: las ocho bobinas CORC suman unas 125 t.

## Requisitos del scorer para la próxima producción

Para no tener que volver a correr la producción si después aparece otra
pregunta, el cambio de C++ debería registrar todo esto en una sola pasada:

- **R1. Acumulación por evento (Camino A).** Sumar la edep de cada órgano y
  de cada categoría dentro del evento, y en `EndOfEventAction` llenar
  S1/S2/N con el total del evento. Da el error estándar correcto y habilita
  el atajo R=1 de la Fase 7.
- **R2. Q(L).** Acumular `edep·Q(L)` por paso (ICRP 60 Q(L), con LET en
  agua) y además **la edep por órgano en bins de LET** (por ejemplo, 30 bins
  logarítmicos de 0.1 a 1000 keV/µm). Con el espectro de LET se puede
  aplicar cualquier función de calidad después (ICRP 60, NASA, RBE para
  efectos deterministas) sin volver a simular.
- **R3. Desglose por tipo de partícula que deposita** (p, α, iones Z>2, e±/γ
  y retrocesos inducidos por neutrones): sirve para interpretar resultados
  y para probar ponderaciones alternativas.
- **R4. Desglose por origen del secundario** (creado en casco, bobinas,
  fantoma o vacío): dice cuánta dosis agregan las propias bobinas, clave
  para comparar blindaje activo y pasivo.
- **R5. Pesos de traza.** Respetarlos y registrarlos, para poder sesgar la
  fuente hacia la nave (reducción de varianza).
- **R6. Contadores de transporte:** primarios cortados por el límite de
  longitud (con su energía), primarios que llegan al casco, a la cabina y
  al fantoma, y fracción de retrodispersión.
- **R7. Fluencia en una superficie alrededor del fantoma**, por partícula y
  energía. Permite recalcular la dosis con coeficientes de conversión
  fluencia-dosis (ICRP 116/123) como validación independiente.
- **R8. Energía muestreada dentro del bin** según el espectro real (en vez
  de la media geométrica), guardando la energía de cada evento. Así
  `R̄_bin × W_bin` estima `∫R(E)Φ(E)dE` sin error de discretización y los
  bins solo sirven de estratificación.
- **R9. Procedencia** en la cabecera de cada salida y en el manifiesto:
  commit de git, hash del binario, macro completa, modo angular, radio de
  la esfera, sha256 del mapa y del GDML, physics list, semillas, número de
  hilos y sexo del fantoma. El coordinator debe rechazar resultados sin
  procedencia válida.
- **R10. AM y AF**, con la malla de scoring correcta para cada sexo, los
  datos de órganos de cada sexo y los nombres de órgano en la salida.
- **R11. Tiempo por evento y CPU**, para el modelo de costo del coordinator.
- **R12. Totales por evento de cada categoría** (un archivo de N ×
  categorías), para estimar la covarianza entre escudo y control con
  semillas comunes (CRN) y calcular η.

Nota técnica (2026-10-01): `ICRP110UserScoreWriter` divide por `joule`
**cualquier** magnitud que vuelca, no solo la energía. Un `trackLength`
volcado con él salió en mm/6.24e12. Cualquier scorer nuevo que pase por
ese writer tiene que corregirlo (test T5 de `plan_barrido.md`).

Ya disponible sin cambios: dosis en todos los órganos (incluidos piel,
cristalino y los demás tejidos con w_T), suficiente para la dosis efectiva
completa y para métricas de efectos deterministas.

## Orden recomendado

Versión detallada: los pilotos en [`plan_piloto.md`](plan_piloto.md) y la
especificación del barrido en [`plan_barrido.md`](plan_barrido.md).

1. Decidir: ley coseno como default, radio de la esfera y dominio del mapa.
2. Un solo cambio de C++ con R1–R11, más tests: comparar contra una corrida
   radial vieja con semilla fija para verificar que la edep total no cambia
   salvo por el modo angular.
3. Actualizar workers e imagen, y que el coordinator exija procedencia (R9).
4. Nueva producción (AM+AF). Repetir el piloto de la Fase 7 (ya sin el
   atajo) y revisar si la Fase 8 sigue haciendo falta (con R8 debería
   bastar con pocos bins).
