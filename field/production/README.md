# Archivos de producción versionados

Excepción deliberada a la regla general del proyecto ("no versionar
binarios regenerables", ver `AGENTS.md`/`field/README.md`): estos archivos
sí se versionan, para que clonar el repo + compilar `ActiveShield_Sim`
alcance para correr `geant4/ActiveShield_Sim/scripts/run_organ_sweep.py`
sin instalar Elmer, sin instalar `field/.venv`, y sin regenerar nada —
importante para quien tenga una máquina mucho más lenta para el pipeline
de mallado/FEM. `field/generated/` sigue sin versionarse; esto no cambia
ese criterio, es una carpeta aparte con una regla propia en `.gitignore`
(`!field/production/**`).

**Geometría de la v2 (2026-10-31):** `crewhat_niac_array.gdml` y sus
manifiestos (`crewhat_niac_array.manifest.json`, `.mesh-manifest.json`,
`_materials.json`) son la disposición de NIAC con la masa corregida (15.6 t
por bobina), generada desde `field/examples/crewhat_niac_array.json` (ver
`field/README.md`, «Disposición de NIAC»). SHA256 del GDML:
`39c6a87632342fe37fe2f30dd910861dc7c697b060937dbfa2a2eca53d5dac80`.
`crewhat_niac_array_current_paths.json` son sus trayectorias de corriente
(SHA256 `705de9e8…71e53`), la entrada de `compute_field_volumetric.py`:
con ella, todas las PCs calculan el mismo mapa sin correr Gmsh.
**Mapa de campo de la v2, candidato (2026-10-31):**
`crewhat_niac_bs_30m_0.25.field-manifest.json` es el manifiesto del mapa
de Biot-Savart volumétrico.
- **Características:** ±30 m, paso de 0.25 m, 6 × 3 filamentos, generado
  en una PC del laboratorio en 208 s.
- **El mapa no está en el repositorio:** pesa 609 MB (171 MB comprimido) y
  supera el límite de GitHub. Hay una copia en el Drive del equipo (carpeta
  «version 2»).
- **SHA256 del mapa:**
  `3e0cd3aee094cc91075aa957585a9ef5311a524357f1c2bb71fa68f9e7d300ed`.
- **Comprobado en la laptop:**
  - la copia descargada tiene ese hash;
  - 1000 nodos al azar coinciden con un recálculo directo en 5·10⁻⁸ (el
    redondeo a 7 cifras);
  - Geant4 lo carga en 42 s, con 1.05 GB de RAM y una esfera de 18 m.
- **Versión binaria (`.bmap`, 2026-10-31):** el mismo mapa en float32,
  168 MB (114 MB con gzip); Geant4 la lee directo y arranca en la mitad del
  tiempo. Manifiesto: `crewhat_niac_bs_30m_0.25.bmap-manifest.json`, con el
  sha256 del texto de origen y la diferencia máxima con él (6·10⁻⁸).
  SHA256 del `.bmap`: `6149d2103e3368b23c2097ab31583ff54c15c5c7f21f7b288489cc9daa32ba75`.
  Se obtiene con `field/map_to_binary.py` desde el `.map`, o directo del
  generador con una salida `.bmap`. Está publicado sin comprimir en el
  release
  [`campo-niac-bs-30m-v1`](https://github.com/s7even-silva/iac-project/releases/tag/campo-niac-bs-30m-v1)
  de GitHub (2026-11-02):
  `gh release download campo-niac-bs-30m-v1 -p niac_bs_30m_0.25.bmap`, y
  después comprobar el SHA256 con `sha256sum`.
- **Para regenerarlo** (idéntico salvo el redondeo):
  ```bash
  field/.venv/bin/python field/compute_field_volumetric.py field/production/crewhat_niac_array_current_paths.json \
    niac_bs_30m_0.25.map --half-size 30 --spacing 0.25 --filaments 6 3
  ```

Pasa a producción cuando P1 cierre los pasos 2 y 3.

**Aviso (2026-10-04): los demás archivos no son la geometría de la v2.**
El arreglo `crewhat_corc_array` y sus mapas usan el patrón Halbach K=1, que
no es la disposición de CREW HaT descrita en el reporte NIAC, y sus bobinas
pesan 77.9 t cada una
frente a las 15.6 t de NIAC (hallazgos A4 y B9 en
[`docs/bitacora/auditoria_2026-09-30.md`](../../docs/bitacora/auditoria_2026-09-30.md)).
Se conservan para reproducir la v1 y como variante de comparación en P1;
la geometría y el mapa de la v2 salen de P1, paso 0
([`plan_piloto.md`](../../docs/bitacora/plan_piloto.md), D9).

**Corrección importante (2026-09-12), léela antes de usar estos
archivos:** el arreglo de 8 bobinas de aquí es la variante **CORC**
(winding pack 0,67m), **no** la cinta 12mm (1,43m) que el equipo había
decidido usar primero — descubierto al preparar este directorio,
revisando el JSON fuente. El arreglo completo nunca se ensambló con la
cinta 12mm; solo existen pilotos de una sola bobina con esa variante. Ver
`AGENTS.md`, sección "Corrección importante... el arreglo de 8 bobinas
siempre fue CORC", para el detalle completo.

## Qué hay aquí

| Archivo | Qué es | SHA256 |
|---|---|---|
| `crewhat_elmer_fullscale.map` | Campo de producción actual: Elmer FEM, arreglo CORC, escala real de nave (padding=3,5m/air-size=0,30, half-size **anisotrópico** X=11,3m/Y=13,3m/Z=7,6m — ver nota más abajo) | `40cf3fa85aa36d663242f88d9f46fb84ffd0dcb74829d83a6616d36fd1259f15` |
| `crewhat_niac_max.map` | Campo anterior (Biot-Savart regularizado, mismo arreglo CORC, half-size=13m/spacing=0,75m) — conservado para comparación explícita, ya no es el default | `73409749dfa64cfa6f506efa19606737856a4aec50a1e160d3f6781e4c6f35f6` |
| `crewhat_corc_array.gdml` | Geometría sólida de las 8 bobinas CORC (material HTS homogeneizado real), para `/spacecraft/coilGeometry` | `0161a0b9f75315374f26ebb56f5d5a37f3e8996943c8272c7fbbcb4c41896b3b` |
| `crewhat_corc_array_materials.json` | Materiales usados por el GDML de arriba | — |
| `crewhat_corc_array_config.json` | Config fuente (`crewhat_halbach_array_pilot.json` original) que generó la geometría — de aquí sale la confirmación de que es CORC, no cinta | — |
| `*.manifest.json` / `*.field-manifest.json` | Manifiestos de generación (hashes de fuente/generador, parámetros) de cada script — mismo criterio de trazabilidad que `field/generated/` | — |

Ambos `.map` corresponden exactamente a la misma geometría/corriente
(1×10⁷ A/bobina, sin escalar) que `crewhat_corc_array.gdml` — mismo
`array_current_paths.json` de origen (ver los manifiestos), consistentes
entre sí.

**Por qué el `.map` de Elmer ya no es un cubo (2026-09-12, tercera
iteración de este mismo archivo — primero ±7,2m, luego ±7,6m cúbico,
ahora anisotrópico):** el dominio mallado de Elmer (`padding=3,5m` sobre
el conductor) llega a `X:±11,8m, Y:±13,8m, Z:±7,8m` — no es un cubo,
porque el propio arreglo de bobinas tampoco lo es: el anillo Halbach vive
principalmente en el plano XY (radio 8m), así que se extiende mucho más
ahí que a lo largo de Z (el eje de la nave). Las dos primeras versiones
de este archivo usaban un `.map` **cúbico** (mismo half-size en los 3
ejes) — quedaba limitado por el eje más corto (Z), y no era solo
"desperdiciar margen": el anillo de bobinas (y, desde que
`/spacecraft/coilGeometry` se importa por defecto, su sólido físico
real) se sale del cubo en X/Y, así que cualquier secundario cargado que
llegara ahí leía campo cero (fuera de dominio) exactamente donde debería
haber campo fuerte cerca del conductor — un hueco físico real, no solo
cosmético.

**Corregido:** `elmer_array_to_map.py` ahora acepta `--half-size X Y Z`
(3 valores) además del caso cúbico de 1 valor. El `.map` actual usa
X=11,3m/Y=13,3m/Z=7,6m — margen de ~0,5m contra el límite real de malla
en X/Y, 0,235m en Z (igual que antes), 0,66m sobre la esfera fuente de
la nave real (~6,94m). Reusa la MISMA solución Elmer ya calculada — no
hizo falta remallar ni resolver de nuevo. Verificado: 700 de 82.720 nodos
(0,85%) rellenados por estar dentro de un conductor (ver
`_fill_conductor_gaps()`), dentro del 5% tolerado; el campo máximo en la
grilla ahora es 6,25T (antes, con el cubo, esa región ni se muestreaba).
**Pendiente de verificar en vivo con Geant4** (el formato se comprobó
por separado — cuenta de filas exacta, todo finito — pero no se pudo
cargar con `ICRP110phantoms` porque el directorio de build estaba
ocupado con el piloto de 8 bins al momento de este cambio).

## Cómo se generaron (para regenerar o auditar, no necesario para usar)

```bash
# Geometria (field/.venv, no geant4_env)
python3 field/generate_ellipse_array.py field/examples/crewhat_halbach_array_pilot.json field/generated/crewhat_halbach_array_production
# GDML solido (requiere mesh_swept.py + mesh_to_gdml.py, ver field/README.md)

# Campo Biot-Savart
python3 field/compute_field_ellipse_array.py field/generated/.../array_current_paths.json crewhat_niac_max.map --half-size 13.0 --spacing 0.75

# Campo Elmer FEM (requiere Elmer instalado, scripts/install.sh --with-elmer)
python3 field/mesh_exterior.py field/generated/crewhat_halbach_array/halbach_array.msh domain.msh --padding 3.5 --air-size 0.30 --threads 8
ElmerGrid 14 2 domain.msh -out elmer_mesh
OMP_NUM_THREADS=1 ElmerSolver case.sif   # case.sif copiado de una corrida Elmer previa del mismo arreglo
python3 field/elmer_array_to_map.py elmer_mesh/elmer_pilot_air_t0001.vtu crewhat_elmer_fullscale.map --half-size 11.3 13.3 7.6 --spacing 0.5
```

Detalle completo, por qué estos parámetros y no otros, y el hallazgo de
que Biot-Savart sobreestima la dosis 36-48% frente a Elmer en esta
geometría: `docs/bitacora/activeshield_sim_historia.md`, sección "Error de
campo vs. error de dosis en Elmer, y extensión a escala real". **Esa cifra
no se reprodujo el 2026-09-30** (0.93 ± 0.08 a 562 MeV, con ley coseno y 3
semillas). Ver `geant4/ActiveShield_Sim/docs/modelo_realista.md`.
