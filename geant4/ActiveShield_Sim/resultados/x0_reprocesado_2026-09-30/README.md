# Barrido de 600 reprocesado en x=0 (2026-09-30)

**No son dosis físicamente válidas. No citarlas como dosis absolutas.**

## Qué es

Las filas con `offset_x_m = 0` del barrido de 600 (apuntado radial,
10000 eventos por corrida), agregadas de nuevo con `aggregate_organ_doses.py`
ya corregido (ver `docs/bitacora/auditoria_2026-09-30.md`):

- vista por órgano sin el factor N (bug A3);
- grilla de bins tomada de los datos, control de duplicados y bins
  ausentes reportados (B1–B3).

Se usó solo x=0 porque es la única posición donde la malla de scoring
estaba sobre el fantoma (bug A1): las filas con offset ≥1 m miden aire.

## Entrada

`entrada_x0_coordinator_raw.csv`: filas con x=0 de
`coordinator_raw/results/job_*/*/results.csv`, es decir, los 323 trabajos
descargados del coordinator (no los 600: el tarball completo no está en
este repo). Son 68 corridas en x=0, con todos los bins presentes:

| Especie | Repeticiones completas en x=0 |
|---|---|
| GCR_H/min | 1 (rep0; reps 1–2 con 6 de 8 bins) |
| GCR_He/min | 2 (rep0, rep1; rep2 con 7 de 8) |
| SEP_p/max | 3 (rep0–rep2; rep3 con 1 de 8) |

Comando:

```bash
python3 ../../scripts/aggregate_organ_doses.py \
  --results entrada_x0_coordinator_raw.csv --out resultados_organo_agregados_x0.csv
```

Después se renombraron las otras tres salidas con el sufijo `_x0`.

## Por qué los valores siguen siendo incorrectos

Todos los primarios se generaron apuntando al origen (bug A2), mientras
que el peso `π R² Φ` supone entrada con ley coseno. En x=0 el fantoma
recibe casi todos los primarios que el campo no desvía, así que la dosis
sale inflada. Ejemplo: colon GCR = 0.156 Sv/día, cuando la referencia de
espacio profundo es del orden de 1 mSv/día.

El factor de inflación **depende de la energía y del campo**. En la prueba
de 562 MeV con campo, la dosis por primario fue 7.3e-14 J con apuntado
radial y 3.1e-14 J con ley coseno. Por eso no existe un factor único que
corrija los resultados en post-proceso: hay que volver a simular. Ver
`docs/bitacora/plan_barrido_corregido.md`.

Además, las incertidumbres de SEP son enormes (H% del 67% al 430%) y
GCR_H bins 6–7 tienen una sola repetición (`bins_R1_sin_varianza`).

## Para qué sirve

Solo como referencia interna del pipeline: comprobar que el agregador
corregido produce valores coherentes entre vistas (el órgano 43 pasó de
1967 a 0.197 Gy/día al quitar el factor N) y para comparar contra el
barrido corregido cuando exista.
