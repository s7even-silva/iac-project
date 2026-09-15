#!/usr/bin/env python3
"""Pide el tail del log en vivo de un job en curso, sin acceso SSH a la
maquina del worker -- diagnostico para el caso real que motivo esto
(2026-09-16, ver AGENTS.md "los logs no ayudan porque no muestran nada"):
un job podia estancarse durante horas sin que nadie pudiera ver que
estaba pasando dentro del subprocess de Geant4 hasta matarlo y perder el
avance.

Mecanismo completo (mismo patron que cancel_job.py, viaja por heartbeat
porque el worker esta detras de NAT sin puerto expuesto):
1. Este comando marca jobs.log_requested=1 via POST /jobs/{id}/request-log
   (ver request_job_log() en db.py).
2. heartbeat_loop() del worker ve request_log=true en la respuesta de su
   proximo heartbeat (hasta 30s de espera) y sube el tail de su log activo
   con un POST aparte a /jobs/{id}/log (ver report_log() en worker.py).
3. Este comando espera esa subida haciendo poll a GET /api/v1/jobs y la
   imprime cuando log_tail_updated_at cambia -- no requiere una segunda
   invocacion manual.

Uso:
    # Pedir y esperar el log del job 137 (coordinator de produccion por default):
    python3 request_job_log.py 137

    # Contra otro coordinator (ej. pruebas locales):
    python3 request_job_log.py 137 --coordinator-url http://127.0.0.1:8000

    # Sin esperar la respuesta (solo dispara la solicitud):
    python3 request_job_log.py 137 --no-wait
"""
import argparse
import sys
import os
import time

import requests

DEFAULT_COORDINATOR_URL = "https://coordinator.vlaboratory.org"
DEFAULT_WAIT_TIMEOUT_S = 90  # heartbeat cada 30s + red -- generoso, no ajustado
POLL_INTERVAL_S = 5


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_id", type=int, help="job_id a inspeccionar (ver GET /api/v1/jobs)")
    parser.add_argument("--coordinator-url", default=DEFAULT_COORDINATOR_URL,
                         help=f"default: {DEFAULT_COORDINATOR_URL}")
    parser.add_argument("--worker-token", default=os.environ.get("WORKER_TOKEN"),
                         help="X-Worker-Token, si el coordinator lo exige (ver WORKER_TOKEN en AGENTS.md)")
    parser.add_argument("--no-wait", action="store_true",
                         help="solo dispara la solicitud, no espera ni imprime el log")
    parser.add_argument("--wait-timeout", type=float, default=DEFAULT_WAIT_TIMEOUT_S,
                         help=f"segundos a esperar la subida del log (default: {DEFAULT_WAIT_TIMEOUT_S})")
    args = parser.parse_args()

    if args.job_id <= 0:
        parser.error("job_id debe ser positivo")
    headers = {"X-Worker-Token": args.worker_token} if args.worker_token else {}
    base = args.coordinator_url.rstrip("/")
    url = f"{base}/api/v1/jobs/{args.job_id}/request-log"
    try:
        resp = requests.post(url, headers=headers, timeout=15)
    except requests.RequestException as exc:
        sys.exit(f"No se pudo contactar al coordinator ({url}): {exc}")

    if resp.status_code == 404:
        sys.exit(f"job {args.job_id} no existe.")
    if resp.status_code == 409:
        sys.exit(f"job {args.job_id} no esta 'claimed'/'running' con un worker asignado -- nada que pedir "
                  "(ya termino, o todavia esta pending).")
    try:
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict) or "job_id" not in body or "claimed_by" not in body:
            raise ValueError("Respuesta de solicitud invalida")
    except (requests.RequestException, ValueError) as exc:
        sys.exit(f"Solicitud no confirmada: {exc}")
    print(f"Log solicitado para job {body['job_id']} (worker: {body['claimed_by']}).")
    if args.no_wait:
        return
    print(f"Esperando hasta {args.wait_timeout:.0f}s a que el worker suba el tail "
          f"(llega en su proximo heartbeat, hasta 30s + red)...")

    deadline = time.monotonic() + args.wait_timeout
    while time.monotonic() < deadline:
        try:
            jobs_resp = requests.get(f"{base}/api/v1/jobs", headers=headers, timeout=15)
            jobs_resp.raise_for_status()
            jobs = jobs_resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"(fallo consultando /jobs, reintentando: {exc})")
            time.sleep(POLL_INTERVAL_S)
            continue
        job = next((j for j in jobs if j.get("job_id") == args.job_id), None)
        if job is None:
            sys.exit(f"job {args.job_id} ya no existe en la cola.")
        if job.get("log_tail"):
            print(f"\n--- log de job {args.job_id}, actualizado {job.get('log_tail_updated_at')} ---")
            print(job["log_tail"])
            return
        time.sleep(POLL_INTERVAL_S)
    sys.exit(f"Sin respuesta del worker tras {args.wait_timeout:.0f}s -- puede estar genuinamente "
             "sin conexion, o el job pudo haber terminado/reencolado en el intervalo.")


if __name__ == "__main__":
    main()
