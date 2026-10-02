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
