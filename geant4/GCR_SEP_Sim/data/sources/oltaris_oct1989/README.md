# Fuente alternativa: evento histórico de octubre de 1989 (OLTARIS)

Carpeta preparada para activar esta fuente en cuanto se apruebe el acceso a
OLTARIS (bloqueado sin fecha estimada al momento de escribir esto — ver
`CLAUDE.md`, sección de decisiones pendientes). Mientras tanto queda vacía
(el `.gitkeep` es solo para que la carpeta exista en git).

## Por qué esta fuente, y en qué difiere de SPENVIS/ESP-PSYCHIC

El evento del 19-24 de octubre de 1989 es uno de los eventos de partículas
solares (SEP) más intensos medidos — un dato histórico real, no una
construcción estadística. Es más citable que un "Worst Case Event"
probabilístico (lo que da ESP-PSYCHIC hoy), pero **no reemplaza el GCR**
(ISO-15390 sigue siendo la fuente de GCR — Oct-1989 es un evento SEP, no
tiene componente GCR). Solo aplicaría a los dos archivos `sep_proton_*`, no
a los cuatro `gcr_*`.

Conceptualmente son el mismo tipo de cantidad (fluencia de UN evento
puntual, no una tasa continua), así que la fórmula de normalización de
dosis ya diseñada para SEP en `CLAUDE.md`
(`dosis_Gy_del_evento = dosis_sim × (fluencia_evento × área_fuente) / N`,
sin factor de tiempo) aplica sin cambios conceptuales — solo cambia qué
número entra como fluencia del evento.

## Qué archivos debe tener esta carpeta

Cuando se exporte el espectro de OLTARIS, guardar aquí exactamente estos
dos archivos (incluso si "solar max"/"solar min" no aplican realmente a un
evento histórico puntual — usar el mismo espectro en ambos, ya que Oct-1989
fue un evento único, no depende de la fase del ciclo solar como GCR):

- `sep_proton_solarmax.csv`
- `sep_proton_solarmin.csv`

Formato esperado por `SpectrumSampler` (ver `include/SpectrumSampler.hh`):
CSV de **dos columnas, energía y flujo diferencial**, cualquier separador
(coma o espacio), líneas que empiecen con `#` se ignoran como comentario.
No importan las unidades exactas del flujo (el sampler solo necesita la
*forma* de la distribución para construir su CDF), pero sí hay que anotar
cuáles son en el checklist para la normalización de dosis absoluta
(`RunAction.cc`, pendiente de implementar).

## Cómo activar esta fuente una vez completa

Desde `geant4/GCR_SEP_Sim/`:

    python3 scripts/select_spectrum_source.py oltaris_oct1989 --only sep_proton_solarmax.csv sep_proton_solarmin.csv

(usa `--only` para no tocar los 4 CSV de GCR, que se quedan en `spenvis/`).
Después, volver a correr `cmake ..` dentro de `build/` (no basta con
`make -j`, ver nota en `scripts/select_spectrum_source.py`) para que el
binario recoja los CSV actualizados.

## Checklist de qué anotar al exportar

Igual que la Parte 2 de `docs/checklist_espectros_reales.md`, pero sin
duración de misión ni nivel de confianza (no aplican a un evento histórico
fijo):

- [ ] Especies/energías exportadas de OLTARIS para el evento Oct-1989.
- [ ] Unidades exactas del export (flujo diferencial vs. integral).
- [ ] Rango de energía exportado (MeV, min-máx).
- [ ] Captura de pantalla de la configuración usada en OLTARIS.
