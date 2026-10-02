"""Constantes de barrido compartidas por los scripts de geant4/.

Un solo lugar para los valores que "todos los scripts deben usar por
defecto" -- si el numero de eventos por defecto cambia, se cambia aqui
una vez.

Uso desde un script en geant4/<proyecto>/scripts/:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    import sweep_config

    parser.add_argument("--n-events", type=int, default=sweep_config.DEFAULT_N_EVENTS)

Hasta la v1 este archivo tambien servia a GCR_SEP_Sim (BASE_SEED_GCR_SEP_SIM,
DEFAULT_REPEATS); ese proyecto quedo en el tag v1-archivo.
"""

# Eventos por corrida (/run/beamOn) por defecto de run_organ_sweep.py. El
# numero de produccion lo fija el plan piloto (P2/P3), no este default.
DEFAULT_N_EVENTS = 10000

# Semilla base para las semillas deterministicas por corrida/repeticion.
# No cambiarla: las semillas de las corridas ya hechas dependen de ella.
BASE_SEED_ACTIVE_SHIELD_SIM = 20260907  # fecha de inicio de ActiveShield_Sim (2026-09-07)
