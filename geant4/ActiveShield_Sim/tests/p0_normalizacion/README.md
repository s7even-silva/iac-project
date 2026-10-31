# P0: dosis absoluta frente a ICRP 116 (preparado, sin correr)

`p0_icrp116.py` corre el fantoma AM desnudo con fuente isótropa (ley
coseno) en las energías candidatas de P0 y calcula el coeficiente de dosis
absorbida por unidad de fluencia de cada categoría, en pGy·cm², con su SE.
Usa el scorer por evento (`/eventStats/*`).

**No se corre hasta tener (estado al 2026-10-31):**
- **Las energías, eventos y semillas**, fijados de antemano. Las de
  `POINTS` en el script son candidatas.

D7 ya está decidido: ±10% en órganos grandes y ±30% en mama y tiroides
(`plan_piloto.md`, D7).

```bash
python3 p0_icrp116.py run --out-dir DIR --events 3000000 --seeds 1 --threads 20
python3 p0_icrp116.py analyze --out-dir DIR
```

`run` salta los puntos que ya tienen `EventStats.tsv`, así que una corrida
cortada se retoma con el mismo comando. `--points proton_1000 alpha_100`
corre solo esos puntos, para repartirlos entre PCs del laboratorio; la
semilla depende del índice del punto en `POINTS`, no del filtro, así que
repartirlos no cambia ningún resultado. Para analizar, juntar las carpetas
de cada punto en un mismo `--out-dir`.

**Nota: qué se compara.** Órganos individuales que ICRP 116 tabula
(pulmones, colon, pared del estómago, médula roja, hígado; mama como
descriptivo). No se comparan las categorías propias `remainder_tissues` ni
`total_body`. Ver P0 en `docs/bitacora/plan_piloto.md`.

**Referencias en `referencias/`:**
- `icrp116_efectiva_protones.csv` (Tabla A.6) e `icrp116_efectiva_helio.csv`
  (Tabla A.11): dosis efectiva, transcritas de la versión impresa. Sirven
  como control secundario, porque necesitan el fantoma AF.
- `icrp116_organos_iso_am.csv`: 28 órganos, protones y helio, ISO,
  fantoma masculino, en pGy·cm². Es la referencia por defecto de
  `analyze`. Se extrajo del material suplementario v2 de ICRP 116 (el zip
  no se versiona por derechos de autor).
