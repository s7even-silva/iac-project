# Fuente activa: SPENVIS (ISO-15390 + ESP-PSYCHIC)

Fuente de datos activa hoy para los 6 CSV de espectro (GCR y SEP, ambas
fases solares). Ver `docs/checklist_espectros_reales.md` para el
procedimiento completo de exportación desde SPENVIS, y `CLAUDE.md` (raíz
del repo) para el porqué de esta elección (OLTARIS quedó bloqueado sin
fecha de aprobación).

Los 6 CSV en esta carpeta son hoy **placeholders** (idénticos entre fase
max/min) — pendiente reemplazarlos con los exports reales de SPENVIS una
vez completado el checklist.

## Activar esta fuente (ya es la que usa `data/` por defecto)

Desde `geant4/GCR_SEP_Sim/`:

    python3 scripts/select_spectrum_source.py spenvis
