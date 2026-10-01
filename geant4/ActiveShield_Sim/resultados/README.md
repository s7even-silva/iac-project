# Resultados de `ActiveShield_Sim`

Reorganizado el 2026-09-30 tras la auditoría
[`docs/bitacora/auditoria_2026-09-30.md`](../../../docs/bitacora/auditoria_2026-09-30.md).
**Todavía no hay ninguna dosis físicamente válida en este directorio.**
Las dosis correctas requieren el barrido corregido, planificado en
[`docs/bitacora/plan_barrido_corregido.md`](../../../docs/bitacora/plan_barrido_corregido.md).

| Carpeta | Contenido | Estado |
|---|---|---|
| [`historico_barrido600_radial/`](historico_barrido600_radial/) | CSV crudos y manifiestos del barrido de 600 por contribuidor (bryam, eddy, joel), su README original, `LIMITACIONES_BARRIDO_600.md` e `INTERPRETACION_PROTECCION_RADIOLOGICA.md`. | Histórico. Las filas con offset ≥1 m miden aire (malla de scoring fija en el origen) y todas las dosis están infladas por el apuntado radial. |
| [`fase8_binning/`](fase8_binning/) | Datos de convergencia del binning (360 corridas en x=0, 8 a 128 bins), `epsilon_binning_fase8_*` y la propuesta de binning híbrido para SEP_p. | Histórico. Se corrió con apuntado radial: las conclusiones deben revalidarse. |
| [`x0_reprocesado_2026-09-30/`](x0_reprocesado_2026-09-30/) | Las filas x=0 del barrido de 600 agregadas con el agregador corregido. | Solo referencia interna: siguen infladas por el apuntado radial. |
| `coordinator_raw/` (no versionado) | Resultados descargados del coordinator (323 trabajos). | Crudo local. |

Los CSV agregados anteriores (`resultados_organo_agregados_*`,
`resultados_riesgo_estocastico_*`) se eliminaron: estaban mal (la vista por
órgano inflada por N, las filas de offset ≥1 m eran aire) y se pueden
regenerar desde los crudos con `scripts/aggregate_organ_doses.py`. Siguen
disponibles en el historial de git (commit anterior a esta reorganización).

Los documentos históricos (`infra/OPERATIONS_LOG.md`,
`infra/DISTRIBUTED_SWEEP_HISTORY.md`, `infra/coordinator/import_local_results.py`)
mencionan rutas como `resultados/organ_sweep_manifest_bryam.csv`: esos
archivos ahora están en `resultados/historico_barrido600_radial/`.
