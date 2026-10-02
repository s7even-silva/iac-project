# P0: dosis absoluta frente a ICRP 116 (preparado, sin correr)

`p0_icrp116.py` corre el fantoma AM desnudo con fuente isótropa (ley
coseno) en las energías candidatas de P0 y calcula el coeficiente de dosis
absorbida por unidad de fluencia de cada categoría, en pGy·cm², con su SE.
Usa el scorer por evento (`/eventStats/*`).

**No se corre hasta tener:**
- **D7:** la tolerancia, fijada antes de ver datos.
- **Las energías, categorías y comparaciones primarias**, fijadas de
  antemano. Las del script son candidatas.
- **La tabla ISO de ICRP 116** para el fantoma masculino, transcrita a un
  CSV versionado con su fuente y unidades. Columnas: `particula`,
  `energia_mev_por_nucleon`, `categoria` y `coef_pGy_cm2`. Es dosis
  absorbida, no efectiva.

```bash
python3 p0_icrp116.py run --out-dir DIR --events 20000 --seeds 1 --threads 4
python3 p0_icrp116.py analyze --out-dir DIR --reference icrp116_iso_am.csv
```

**Nota: qué se compara.** Órganos individuales que ICRP 116 tabula
(pulmones, colon, pared del estómago, médula roja, hígado; mama como
descriptivo). No se comparan las categorías propias `remainder_tissues` ni
`total_body`. Ver P0 en `docs/bitacora/plan_piloto.md`.

**Referencias en `referencias/`:**
- `icrp116_efectiva_protones.csv` (Tabla A.6) e `icrp116_efectiva_helio.csv`
  (Tabla A.11): dosis efectiva, transcritas de la versión impresa. Sirven
  como control secundario, porque necesitan el fantoma AF.
- Falta el CSV por órgano. Esos coeficientes vienen solo en el material
  suplementario (CD) de la publicación en Sage.
