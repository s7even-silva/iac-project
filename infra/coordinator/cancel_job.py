#!/usr/bin/env python3
"""Cancela un job a mitad de una corrida -- termina el subprocess de
Geant4 del worker que lo tiene asignado, no solo lo reencola.

Este comando usa la API para validar el estado y solicitar la cancelacion
sin acceso directo a la SQLite del servicio. El coordinator lee el flag en
cada heartbeat; no existe una senal en memoria que requiera actualizarse
ademas de la DB. La API evita editar manualmente la DB incorrecta.

Mecanismo completo (ver AGENTS.md, "Remote-kill de un job en curso"):
1. Este comando marca jobs.cancel_requested=1 via POST /jobs/{id}/cancel
   (ver request_job_cancel() en db.py) -- el status del job sigue
   'claimed'/'running' hasta que el worker reporte el resultado real.
2. heartbeat_loop() del worker (hilo separado, corriendo en paralelo al
   subprocess.communicate() que bloquea el hilo principal) ve
   cancel_job_id en la respuesta del heartbeat y activa un Event local.
3. Un hilo watcher dedicado dentro de run_job() (que SI puede reaccionar
   mientras communicate() bloquea) mata el process group del subprocess
   con SIGTERM (y SIGKILL si no responde) en cuanto ve el Event.
4. El job se reporta como fallo ("cancelado por el operador") -- se
   reencola solo (attempt < max_attempts) para que otro worker lo
   retome, sin ningun cambio de logica extra.

Progreso perdido: TODO el avance de esa corrida (no hay checkpointing en
Geant4/run_organ_sweep.py) -- usar solo cuando el avance real ya
conectado es bajo (ver "Tiempo conectado" en el dashboard/GET
/api/v1/jobs antes de cancelar).

A proposito NO surge en dashboard.html -- accion administrativa de
terminal, no un boton de un lado exponible a cualquiera con el link del
dashboard (ver AGENTS.md).

Uso:
    # Cancelar el job 137 (usando el coordinator de produccion por default):
    python3 cancel_job.py 137

    # Contra otro coordinator (ej. pruebas locales):
    python3 cancel_job.py 137 --coordinator-url http://127.0.0.1:8000
"""
import argparse
import sys
import os

import requests

DEFAULT_COORDINATOR_URL = "https://coordinator.vlaboratory.org"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_id", type=int, help="job_id a cancelar (ver GET /api/v1/jobs)")
    parser.add_argument("--coordinator-url", default=DEFAULT_COORDINATOR_URL,
                         help=f"default: {DEFAULT_COORDINATOR_URL}")
    parser.add_argument("--worker-token", default=os.environ.get("WORKER_TOKEN"),
                         help="X-Worker-Token, si el coordinator lo exige (ver WORKER_TOKEN en AGENTS.md)")
    args = parser.parse_args()

    if args.job_id <= 0:
        parser.error("job_id debe ser positivo")
    headers = {"X-Worker-Token": args.worker_token} if args.worker_token else {}
    url = f"{args.coordinator_url.rstrip('/')}/api/v1/jobs/{args.job_id}/cancel"
    try:
        resp = requests.post(url, headers=headers, timeout=15)
    except requests.RequestException as exc:
        sys.exit(f"No se pudo contactar al coordinator ({url}): {exc}")

    if resp.status_code == 404:
        sys.exit(f"job {args.job_id} no existe.")
    if resp.status_code == 409:
        sys.exit(f"job {args.job_id} no esta 'claimed'/'running' con un worker asignado -- nada que cancelar "
                  "(ya termino, o todavia esta pending).")
    try:
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict) or "job_id" not in body or "claimed_by" not in body:
            raise ValueError("Respuesta de cancelacion invalida")
    except (requests.RequestException, ValueError) as exc:
        sys.exit(f"Cancelacion no confirmada: {exc}")
    print(f"Cancelacion solicitada para job {body['job_id']} (worker: {body['claimed_by']}).")
    print("El worker recibe la solicitud en un heartbeat (30s por defecto, mas red y hasta 3s de terminacion) -- "
          "se reporta como fallo: vuelve a pending si quedan intentos, o queda failed.")


if __name__ == "__main__":
    main()
