# Scorer por evento (R1)

Los comandos `/eventStats/*` (`src/EventStatsRunAction.cc`) suman el
depósito de **cada evento** por órgano y por categoría antes de acumular
S1/S2. M cuenta todos los primarios, incluidos los que no depositan.
Detalle en `docs/bitacora/plan_barrido.md`, sección 5. Se apoya en la malla
`PhantomMesh/energyDeposit`, así que la malla tiene que estar definida igual
que en el barrido.

```
/eventStats/enable true
/eventStats/phantomSex male            # igual que /phantom/setScoreWriterSex
/eventStats/phantomSection full
/eventStats/categoryFile event_categories.txt   # scripts/write_event_categories.py
/eventStats/checkpoints 2500,5000,10000         # separados por comas
/eventStats/output EventStats.tsv
/eventStats/perEventFile EventCategories.tsv    # opcional (R12, CRN)
```

`EventStats.tsv` tiene una fila por (checkpoint, órgano o categoría), con
estas columnas:
- `S1_J`, `S2_J2`, `n_nonzero`;
- `max_J` y `max_event_id`, la mayor contribución de un solo evento;
- `mean_J` (= S1/M) y `se_mean_J`, el error estándar de la media por
  primario;
- `S3_J3`, `S4_J4` y `vov`, la varianza relativa de la varianza de MCNP. El
  SE de la categoría se considera confiable con VOV < 0.1; detalle en
  `docs/bitacora/metodo_autodiagnostico_incertidumbre.md`.

El checkpoint `-1` es la corrida completa. Los checkpoints cuentan los
eventos con `event_id < M`, así que no dependen del reparto entre hilos. El
encabezado trae el contador de trazas cortadas por el límite de longitud de
`MagnetEnvelope` (R6).

| Archivo | Qué hace |
|---|---|
| `test_t4_t5.py` | T4/T5 (ctest `event_stats`, ~20 s). Compara S1 con `ICRP110.out` y S1/S2 con el archivo por evento, comprueba que los checkpoints sean acumulados y que `trackLength` salga en mm. |
| `prueba_lotes.py` | Lo mismo partiendo una corrida grande en K lotes por `event_id`, en casos difíciles (SEP cerca del corte, alfas, 10 GeV). Mide ρ, la cobertura del IC95 de una sola corrida y la fracción de corridas que subestiman su SE a menos de la mitad. Con `diagnose` valida la VOV como autodiagnóstico. Resultados en `resultados/lotes_casco_2026-10-01.csv` y `resultados/diagnostico_vov_casco_2026-10-01.csv`. ~30 min. |
| `prueba_atajo_intrarun.py` | Prueba exploratoria del atajo intra-run: SE de una corrida frente a la dispersión entre K semillas, y lo mismo con el Camino B histórico. Resultado del 2026-10-01 en `resultados/` y en `plan_piloto.md` (P2). ~15 min con K=10, M=20000 y 2 hilos. |

```bash
cd geant4/ActiveShield_Sim/build && ctest -R event_stats
python3 ../tests/scorer_por_evento/prueba_atajo_intrarun.py --out-dir /tmp/atajo --seeds 10 --events 20000
```
