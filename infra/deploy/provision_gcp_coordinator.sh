#!/usr/bin/env bash
# Crea una VM e2-micro en GCP para hostear el coordinator 24/7, dentro del
# Always Free Tier (1 e2-micro/mes gratis en us-west1/us-central1/us-east1 --
# ver https://cloud.google.com/free/docs/free-cloud-features#compute).
# Usa el mismo cloud-init-coordinator.yaml que el script de Azure (formato
# estandar, funciona igual en ambos proveedores).
#
# Requiere: gcloud CLI instalado y logueado (gcloud auth login), un proyecto
# con facturacion activa ya configurado como default (gcloud config set
# project <id> -- ver AGENTS.md, seccion "Computo distribuido").
#
# Uso:
#   bash infra/deploy/provision_gcp_coordinator.sh
#   bash infra/deploy/provision_gcp_coordinator.sh --zone=us-central1-a
set -euo pipefail

ZONE="${ZONE:-us-central1-a}"
VM_NAME="${VM_NAME:-geant4-coordinator}"
MACHINE_TYPE="${MACHINE_TYPE:-e2-micro}"

for arg in "$@"; do
  case "$arg" in
    --zone=*) ZONE="${arg#*=}" ;;
    *) echo "Argumento desconocido: $arg" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/google-cloud-sdk/bin:$PATH"

command -v gcloud >/dev/null 2>&1 || { echo "ERROR: gcloud no encontrado. Instalalo primero." >&2; exit 1; }

PROJECT="$(gcloud config get-value project 2>/dev/null)"
[ -n "$PROJECT" ] || { echo "ERROR: no hay proyecto default. Corre 'gcloud config set project <id>' primero." >&2; exit 1; }

echo "==> Proyecto activo: $PROJECT"
echo "==> Verificando facturacion habilitada"
gcloud billing projects describe "$PROJECT" --format="value(billingEnabled)" | grep -q True || {
  echo "ERROR: el proyecto '$PROJECT' no tiene facturacion habilitada." >&2
  exit 1
}

echo "==> Creando regla de firewall para el puerto 8000 (API del coordinator)"
gcloud compute firewall-rules create geant4-coordinator-allow-8000 \
  --allow=tcp:8000 \
  --target-tags=geant4-coordinator \
  --description="ActiveShield_Sim compute coordinator API" \
  2>&1 | grep -v "already exists" || true

echo "==> Creando VM '$VM_NAME' ($MACHINE_TYPE) en $ZONE con cloud-init"
gcloud compute instances create "$VM_NAME" \
  --zone="$ZONE" \
  --machine-type="$MACHINE_TYPE" \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --tags=geant4-coordinator \
  --metadata-from-file=user-data="$SCRIPT_DIR/cloud-init-coordinator.yaml"

IP=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

cat <<EOF

==================================================================
VM creada. IP publica: $IP

El cloud-init tarda 1-2 minutos en clonar el repo, crear el venv e
iniciar el servicio systemd. Verificar:

  gcloud compute ssh $VM_NAME --zone=$ZONE --command='sudo systemctl status geant4-coordinator'
  curl http://$IP:8000/api/v1/health

Apuntar los workers a:
  COORDINATOR_URL=http://$IP:8000

IMPORTANTE (ver AGENTS.md, riesgos aceptados): sin autenticacion de
workers todavia. El firewall quedo abierto al puerto 8000 desde
cualquier IP -- para restringirlo a IPs conocidas:
  gcloud compute firewall-rules update geant4-coordinator-allow-8000 \\
    --source-ranges=<tu-ip>/32

Para destruir todo cuando termines (borra la VM -- la base SQLite y
los resultados subidos se pierden si no se respaldaron antes):
  gcloud compute instances delete $VM_NAME --zone=$ZONE --quiet
  gcloud compute firewall-rules delete geant4-coordinator-allow-8000 --quiet
==================================================================
EOF
