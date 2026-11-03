# P1 paso 3: dosis frente al radio de la esfera fuente (preparado, sin correr)

`p1_radio.py` compara la dosis de cuerpo entero con esferas fuente de 14, 16
y 18 m, con el mapa final, en protones de 70 y 100 MeV sobre el fantoma AM en
x = 0 y x = 4 m. Diseño, criterio y costo en `docs/bitacora/plan_piloto.md`
(P1, «Diseño del paso 3»), fijados el 2026-10-31 antes de correr.

Necesita el binario compilado después del 2026-11-03 (lista de física
`QGSP_INCLXX_HP` y comando `/spacecraft/envelopeMaxTrackLength`; si falta
alguno, la corrida se detiene) y el
mapa candidato, de preferencia en binario (`niac_bs_30m_0.25.bmap`, en
el release `campo-niac-bs-30m-v1` de GitHub; manifiesto y comando de
descarga en `field/production/`).

```bash
cd geant4/ActiveShield_Sim
MAPA=/ruta/niac_bs_30m_0.25.bmap
# 1. Una sonda por caso (unos minutos): fija N de cada corrida en sonda.json.
python3 tests/p1_radio/p1_radio.py sonda --case p70_x0 --out-dir DIR --field-map $MAPA
# 2. Las corridas: control, R14, R16 y R18. Cada una se puede partir entre PCs.
python3 tests/p1_radio/p1_radio.py run --case p70_x0 --out-dir DIR --field-map $MAPA
python3 tests/p1_radio/p1_radio.py run --case p70_x0 --out-dir DIR --field-map $MAPA \
    --runs R18 --parts 4 --part 2
# 3. Juntar las carpetas DIR de todas las PCs y analizar.
python3 tests/p1_radio/p1_radio.py analyze --out-dir DIR
```

Casos: `p70_x0`, `p100_x0`, `p70_x4`, `p100_x4`. Una PC que corre parte de
un caso necesita el `sonda.json` de ese caso (copiar `DIR/<caso>/sonda.json`).
`run` salta las partes que ya tienen `EventStats.tsv`, así que una corrida
cortada se retoma con el mismo comando. Cada parte lleva su semilla, el
radio, el límite de traza y el sha256 del mapa en `config.json`; `analyze`
rechaza mezclas de mapas y casos con partes faltantes.

**Lista de física (2026-11-03).** Cada corrida exige que `run.log` muestre
la lista de `design_parameters.PHYSICS_LIST` (`QGSP_INCLXX_HP`); con un
binario anterior o con `PHYSLIST` puesta, se detiene. La lista queda en
`sonda.json` y en el `config.json` de cada parte: `run` rechaza una sonda
de otra lista (las del 2026-11-02 eran con `Shielding`: repetirlas) y
`analyze`, partes de listas distintas.

`test_p1_analisis.py` comprueba el análisis con corridas sintéticas:
equivalencia con la misma dosis, rechazo con un 6% de diferencia, D4 y la
suma de partes. `--events` (en `sonda` y `run`) es solo para pruebas
cortas.
