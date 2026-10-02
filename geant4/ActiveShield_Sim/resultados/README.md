# Resultados de `ActiveShield_Sim`

Aquí van los CSV del barrido corregido (v2). **Todavía no hay ninguno:**
el barrido empieza cuando se aprueben los pilotos P0–P6 de
[`docs/bitacora/plan_piloto.md`](../../../docs/bitacora/plan_piloto.md).

Los resultados de la v1 salieron de `main` el 2026-10-01 y están en el tag
[`v1-archivo`](https://github.com/s7even-silva/iac-project/tree/v1-archivo/geant4/ActiveShield_Sim/resultados):

| Carpeta (en `v1-archivo`) | Contenido | Por qué no sirve como dosis |
|---|---|---|
| `historico_barrido600_radial/` | CSV crudos y manifiestos del barrido de 600 por contribuidor, con sus notas de limitaciones e interpretación. | Las filas con offset ≥1 m miden aire (malla de scoring fija en el origen) y todas las dosis están infladas por el apuntado radial. |
| `fase8_binning/` | Convergencia del binning (360 corridas en x=0, 8 a 128 bins) y la propuesta de binning híbrido para SEP_p. | Se corrió con apuntado radial; las conclusiones se revalidan en P3. |
| `x0_reprocesado_2026-09-30/` | Filas x=0 del barrido de 600 con el agregador corregido. | Siguen infladas por el apuntado radial. |

`coordinator_raw/` (no versionado) guarda localmente los resultados
descargados del coordinator en la v1.

Detalle de los bugs en
[`docs/bitacora/auditoria_2026-09-30.md`](../../../docs/bitacora/auditoria_2026-09-30.md).
