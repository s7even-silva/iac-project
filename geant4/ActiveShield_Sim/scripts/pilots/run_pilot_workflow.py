#!/usr/bin/env python3
"""Orquestador de las Fases 7->10 del plan estadistico (2026-09-19,
pedido explicito del equipo: "que un piloto, al terminar, ya haga sus
calculos y con sus resultados no bloquee la ejecucion del siguiente
script").

DISEnO: gates, no automatizacion ciega. El plan (docs/bitacora/
plan_estadistico.md) da un umbral numerico EXPLICITO solo en dos de las
cuatro fases (Fase 8: B_8_16<=2.5pp: Fase 10: H_eta,95<=5pp) -- en esas
dos, este orquestador puede avanzar solo cuando el resultado es
claramente favorable (VERDICT_AUTO_CONTINUE, ver pilot_state.py). En
todos los demas casos (Fase 7 siempre, o Fase 8/10 con resultado
limitrofe/desfavorable) el plan explicitamente pide juicio humano -- el
orquestador SE DETIENE con instrucciones exactas de como continuar, en
vez de inventar un criterio que el equipo nunca aprobo.

Esto significa: correr este script NO garantiza que las 4 fases terminen
solas en una sola invocacion -- lo tipico es que se detenga en Fase 7
(que casi siempre da REVISAR, ver run_intrarun_pilot.py) y haya que
retomarlo a mano con --continue-to fase8 despues de que el equipo revise
el reporte. Lo que SI garantiza es que, DENTRO de cada fase, correr +
analizar no requiere intervencion manual -- eso es lo que antes no
pasaba (cada run_faseN.py ya lo resuelve solo).

Uso:
    # Arranca desde Fase 7 (primera vez):
    python3 pilots/run_pilot_workflow.py

    # Retoma desde una fase especifica (despues de revisar un gate a mano):
    python3 pilots/run_pilot_workflow.py --continue-to fase8
    python3 pilots/run_pilot_workflow.py --continue-to fase9 --n-bins 16  # si Fase 8 dijo 16 bins

    # Ver el estado actual sin correr nada:
    python3 pilots/run_pilot_workflow.py --status

Argumentos especificos de cada fase (--n-events, --n-bins, --m-b-csv,
etc.) se pasan tal cual a cada run_faseN.py -- ver --help de cada uno.

RESUME AUTOMATICO (2026-09-20): si la fase que le toca correr tiene un
results/<prefix>_<timestamp>/ con manifest.csv de una corrida anterior
(completa o cortada a mitad, ej. por fin de sesion) y no se paso
--out-dir explicito en los argumentos, este orquestador encuentra solo
el mas reciente (pilot_common.find_latest_out_dir()) y se lo pasa a la
fase -- que a su vez salta las combinaciones ya exitosas (ver
pilot_common.resolve_out_dir()/add_resume_arg()). No hace falta que el
usuario recuerde ni pase el directorio a mano. Para forzar una corrida
nueva desde cero en vez de retomar, pasar --no-resume (se reenvia tal
cual a la fase).
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pilot_common as pc  # noqa: E402
import pilot_state  # noqa: E402

FASES = ["fase7", "fase8", "fase9", "fase10"]
SCRIPT_BY_FASE = {
    "fase7": "run_intrarun_pilot.py",
    "fase8": "run_fase8_binning.py",
    "fase9": "run_fase9_calibracion_mb.py",
    "fase10": "run_fase10_endpoint.py",
}
OUT_DIR_PREFIX_BY_FASE = {
    "fase7": "intrarun_pilot",
    "fase8": "fase8_binning",
    "fase9": "fase9_calibracion_mb",
    "fase10": "fase10_endpoint",
}
PILOTS_DIR = Path(__file__).resolve().parent


def print_status():
    print("Estado actual del workflow (pilots/results/state/):\n")
    for fase in FASES:
        result = pilot_state.read_state(fase)
        if result is None:
            print(f"  {fase}: sin correr todavia")
            continue
        print(f"  {fase}: veredicto={result.veredicto}")
        print(f"    {result.resumen}")
        if result.veredicto != pilot_state.VERDICT_AUTO_CONTINUE:
            print(f"    -> {result.instrucciones_si_no_auto}")
        print()


def run_fase(fase: str, extra_args: list[str]) -> pilot_state.FaseResult | None:
    script = PILOTS_DIR / SCRIPT_BY_FASE[fase]
    args = list(extra_args)

    # Resume automatico: si el llamador no paso --out-dir a mano y hay una
    # corrida anterior de esta fase (completa o cortada), la reusamos --
    # ver docstring del modulo. "--no-resume" en extra_args deshabilita
    # esto explicitamente (se reenvia igual a la fase, que empieza de cero
    # en el mismo directorio nuevo que hubiera generado sin este bloque).
    if "--out-dir" not in args and "--no-resume" not in args:
        latest = pc.find_latest_out_dir(PILOTS_DIR, OUT_DIR_PREFIX_BY_FASE[fase])
        if latest is not None:
            print(f"Resume automatico: retomando {latest}")
            args = ["--out-dir", str(latest)] + args

    print(f"\n{'='*70}")
    print(f"Corriendo {fase} ({script.name})...")
    print(f"{'='*70}\n")
    result = subprocess.run([sys.executable, str(script)] + args, cwd=PILOTS_DIR)
    if result.returncode != 0:
        print(f"\n!! {script.name} termino con exit code {result.returncode} -- "
              f"revisar salida arriba, no se genero estado valido.")
        return None
    return pilot_state.read_state(fase)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--continue-to", type=str, choices=FASES, default=None,
                         help="Empezar desde esta fase (en vez de fase7) -- usar despues de revisar "
                              "un gate a mano y decidir seguir.")
    parser.add_argument("--status", action="store_true",
                         help="Solo mostrar el estado actual (de results/state/), sin correr nada.")
    args, extra_args = parser.parse_known_args()

    if args.status:
        print_status()
        return

    start_idx = FASES.index(args.continue_to) if args.continue_to else 0

    for fase in FASES[start_idx:]:
        result = run_fase(fase, extra_args)
        if result is None:
            print(f"\nWorkflow detenido: {fase} no genero un estado valido (ver salida arriba).")
            sys.exit(1)

        print(f"\n--- Gate de {fase}: veredicto={result.veredicto} ---")
        print(result.resumen)

        if result.veredicto == pilot_state.VERDICT_AUTO_CONTINUE:
            print(f"Automatico: siguiendo a la fase siguiente sin intervencion.")
            continue

        # LIMITROFE / REVISAR / FALLO -- el orquestador se detiene aqui,
        # a proposito (ver docstring del modulo: el plan pide juicio
        # humano en estos casos, no un umbral que este script invente).
        print(f"\n{'!'*70}")
        print(f"WORKFLOW DETENIDO en {fase} (veredicto: {result.veredicto})")
        print(f"{'!'*70}\n")
        print("Como continuar:")
        print(f"  {result.instrucciones_si_no_auto}\n")
        print(f"Resultados completos de esta corrida: {result.out_dir}")
        idx = FASES.index(fase)
        if idx + 1 < len(FASES):
            print(f"\nUna vez decidido, retomar con:")
            print(f"  python3 pilots/run_pilot_workflow.py --continue-to {FASES[idx + 1]} [args de esa fase]")
        sys.exit(0)

    print(f"\n{'='*70}")
    print("Workflow completo: las 4 fases terminaron con AUTO_CONTINUE.")
    print("Ver Fase 22 del plan (Etapa F) para desplegar la expansion de produccion.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
