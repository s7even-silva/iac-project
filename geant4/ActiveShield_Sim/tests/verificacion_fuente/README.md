# Verificación de la fuente, la normalización y la malla (2026-09-30 / 10-01)

Pruebas que respaldan las correcciones de la auditoría
(`docs/bitacora/auditoria_2026-09-30.md`) y la sección "Verificaciones ya
hechas" de `docs/bitacora/plan_piloto.md`. Requieren el binario compilado
con `/gun/angularDistribution`.

Los macros se corren desde un directorio de build que tenga `ICRPdata/` y
`data/` (por ejemplo `build/`, o una carpeta con enlaces simbólicos a
ellos), porque `ICRP110.out` y los volcados se escriben en el directorio
actual y se sobrescriben entre corridas.

| Archivo | Qué hace | Resultado obtenido |
|---|---|---|
| `montecarlo_fuente.py` | Replica en Python el algoritmo de `SampleIsotropicPosition()` (ley coseno y radial) y mide la fluencia en esferas de 30 cm, 4·10⁶ primarios. No usa Geant4. | Ley coseno: 0.990, 1.014, 1.025 y 1.000 de N/(πR²) en x = 0, 1, 2 y 4 m. Radial: 803, 24.6, 6.1 y 1.5. |
| `normalizacion_caja.mac` + `comparar_normalizacion.py` | Protones de 1778 MeV, sin casco (0.001 cm), sin bobinas ni campo, 10⁶ primarios. Cruces y traza en una caja de 50 cm en x=1.5 m, filtro 1000–1800 MeV. | Cruces/esperado = 1.010 ± 0.020; traza/esperada = 1.019 (~5 min con 7 hilos). |
| `dosis_fantoma_desnudo.mac` + `comparar_dosis_analitica.py` | Misma configuración, 4·10⁴ primarios; dosis de cuerpo entero frente a Φ·S/ρ (Bethe). Pasar N como segundo argumento. | 1.83 veces la pura ionización. La corrida de 10⁶ de la fila anterior da 1.72. |
| `comparacion_mallas_y_mapas.py`, `correr_comparacion.sh`, `analizar_comparacion.py` | T1: malla de scoring (x=0 frente a x=1 m, sin campo, 1778 MeV, 30k). T2: dosis con el mapa Biot-Savart frente a Elmer (562 MeV, x=0, 3 semillas por mapa, ley coseno; control con apuntado radial). Salidas en `build/verificacion_fuente/`. | T1: 0.91. T2: Biot-Savart/Elmer = 0.93 ± 0.08 (ley coseno) y 1.03 (radial). ~1 h 10 min en total. |

Nota: hasta el 2026-10-01 `ICRP110UserScoreWriter` dividía por `joule`
cualquier magnitud que volcaba, y `comparar_normalizacion.py` multiplicaba
por 6.2415e12. Desde el arreglo T5, las magnitudes que no son depósito de
energía se vuelcan en su propia unidad (mm, cuentas) y el script las lee tal
cual. Los resultados de la tabla se obtuvieron antes del cambio.

Uso:

```bash
cd geant4/ActiveShield_Sim/build
./ICRP110phantoms ../tests/verificacion_fuente/normalizacion_caja.mac
python3 ../tests/verificacion_fuente/comparar_normalizacion.py
./ICRP110phantoms ../tests/verificacion_fuente/dosis_fantoma_desnudo.mac
cd .. && python3 tests/verificacion_fuente/comparar_dosis_analitica.py build/ICRP110.out 40000
python3 tests/verificacion_fuente/montecarlo_fuente.py
bash tests/verificacion_fuente/correr_comparacion.sh && python3 tests/verificacion_fuente/analizar_comparacion.py
```
