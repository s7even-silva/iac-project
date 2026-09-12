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
| `crewhat_elmer_fullscale.map` | Campo de producción actual: Elmer FEM, arreglo CORC, escala real de nave (padding=3,5m/air-size=0,30, half-size=7,2m/spacing=0,5m) | `9b9344e5b56ed059800afaa3a16bef2136a5e2d71ab41e512d09a72ed84cc9b7` |
| `crewhat_niac_max.map` | Campo anterior (Biot-Savart regularizado, mismo arreglo CORC, half-size=13m/spacing=0,75m) — conservado para comparación explícita, ya no es el default | `73409749dfa64cfa6f506efa19606737856a4aec50a1e160d3f6781e4c6f35f6` |
| `crewhat_corc_array.gdml` | Geometría sólida de las 8 bobinas CORC (material HTS homogeneizado real), para `/spacecraft/coilGeometry` | `0161a0b9f75315374f26ebb56f5d5a37f3e8996943c8272c7fbbcb4c41896b3b` |
| `crewhat_corc_array_materials.json` | Materiales usados por el GDML de arriba | — |
| `crewhat_corc_array_config.json` | Config fuente (`crewhat_halbach_array_pilot.json` original) que generó la geometría — de aquí sale la confirmación de que es CORC, no cinta | — |
| `*.manifest.json` / `*.field-manifest.json` | Manifiestos de generación (hashes de fuente/generador, parámetros) de cada script — mismo criterio de trazabilidad que `field/generated/` | — |

Ambos `.map` corresponden exactamente a la misma geometría/corriente
(1×10⁷ A/bobina, sin escalar) que `crewhat_corc_array.gdml` — mismo
`array_current_paths.json` de origen (ver los manifiestos), consistentes
entre sí.

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
python3 field/elmer_array_to_map.py elmer_mesh/elmer_pilot_air_t0001.vtu crewhat_elmer_fullscale.map --half-size 7.2 --spacing 0.5
```

Detalle completo, por qué estos parámetros y no otros, y el hallazgo de
que Biot-Savart sobreestima la dosis 36-48% frente a Elmer en esta
geometría: `AGENTS.md`, sección "Error de campo vs. error de dosis en
Elmer, y extensión a escala real".
