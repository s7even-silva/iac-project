"""Constantes de barrido compartidas entre proyectos GEANT4 del repo
(GCR_SEP_Sim hoy, ActiveShield_Sim cuando tenga su propio barrido).

Un solo lugar para los valores que "todos los scripts deben usar por
defecto" -- si el numero oficial de eventos del proyecto cambia, se cambia
aqui una vez, no en cada run_sweep.py por separado.

Uso desde un script en geant4/<proyecto>/scripts/:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    import sweep_config

    parser.add_argument("--n-events", type=int, default=sweep_config.DEFAULT_N_EVENTS)

No pongas aqui valores especificos de la geometria de un solo proyecto (ej.
FIELD_VALUES_T de un campo uniforme, o POSITIONS_M del barrido de posicion
del astronauta de GCR_SEP_Sim) -- esos siguen viviendo en el run_sweep.py de
ese proyecto, porque no tiene sentido que ActiveShield_Sim los herede
cuando su espacio de parametros (bobinas Halbach, no campo uniforme) va a
ser distinto.
"""

# Eventos por corrida (/run/beamOn) para el barrido de PRODUCCION real
# (no pilotos). Ver README.md, seccion "Antes de repartir": medido en
# laptop de gama baja, 10000 eventos tardan ~2-10s por corrida segun la
# combinacion -- confirmar de nuevo si cambia la physics list o la
# geometria (mas volumenes = mas lento).
DEFAULT_N_EVENTS = 10000

# Repeticiones por combinacion para poder calcular media/desviacion/IC95%
# (ver README.md, "Division del trabajo del equipo"). 5 es lo acordado
# para el barrido de GCR_SEP_Sim; si ActiveShield_Sim decide un numero
# distinto por su propio presupuesto de computo, sobreescribir ahi, no
# cambiar este default global sin avisar al equipo (afecta la estadistica
# ya usada en corridas anteriores).
DEFAULT_REPEATS = 5

# Semilla base para las semillas deterministicas por corrida/repeticion.
# Usar UNA semilla base por proyecto (no reusar la de GCR_SEP_Sim en
# ActiveShield_Sim) para que sus streams de aleatoriedad no coincidan por
# accidente si algun dia se corren combinaciones con los mismos indices.
BASE_SEED_GCR_SEP_SIM = 20260905       # fecha del pivote de metodologia (2026-09-05)
BASE_SEED_ACTIVE_SHIELD_SIM = 20260907  # fecha de inicio de ActiveShield_Sim (2026-09-07)
