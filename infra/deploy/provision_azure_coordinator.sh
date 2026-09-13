#!/usr/bin/env bash
# Crea una VM pequena en Azure para hostear el coordinator 24/7. El
# coordinator es liviano (FastAPI + SQLite, no computa) -- una VM
# barata (B1s) alcanza de sobra. cloud-init-coordinator.yaml deja el
# servicio corriendo automaticamente al primer arranque (systemd,
# Restart=always).
#
# Requiere: az CLI instalado y logueado (az login), credito de Azure
# activo (ver AGENTS.md, seccion "Computo distribuido").
#
# Uso:
#   bash infra/deploy/provision_azure_coordinator.sh
#   bash infra/deploy/provision_azure_coordinator.sh --location eastus --vm-size Standard_B1s
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-geant4-coordinator-rg}"
LOCATION="${LOCATION:-eastus}"
VM_NAME="${VM_NAME:-geant4-coordinator}"
VM_SIZE="${VM_SIZE:-Standard_B1s}"
ADMIN_USER="${ADMIN_USER:-azureuser}"

for arg in "$@"; do
  case "$arg" in
    --location=*) LOCATION="${arg#*=}" ;;
    --vm-size=*) VM_SIZE="${arg#*=}" ;;
    *) echo "Argumento desconocido: $arg" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v az >/dev/null 2>&1 || { echo "ERROR: Azure CLI (az) no encontrado. Instalalo primero." >&2; exit 1; }
az account show >/dev/null 2>&1 || { echo "ERROR: no hay sesion activa. Corre 'az login' primero." >&2; exit 1; }

echo "==> Cuenta activa:"
az account show --query "{name:name, id:id}" -o table

echo "==> Creando resource group '$RESOURCE_GROUP' en '$LOCATION' (si no existe)"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o table

echo "==> Creando VM '$VM_NAME' ($VM_SIZE) con cloud-init"
az vm create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VM_NAME" \
  --image Ubuntu2404 \
  --size "$VM_SIZE" \
  --admin-username "$ADMIN_USER" \
  --generate-ssh-keys \
  --custom-data "$SCRIPT_DIR/cloud-init-coordinator.yaml" \
  -o table

echo "==> Abriendo puerto 8000 (API del coordinator) -- restringir a IPs conocidas en produccion real"
az vm open-port --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --port 8000 --priority 900 -o table

IP=$(az vm show -d --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --query publicIps -o tsv)

cat <<EOF

==================================================================
VM creada. IP publica: $IP

El cloud-init tarda 1-2 minutos en clonar el repo, crear el venv e
iniciar el servicio systemd. Verificar:

  ssh $ADMIN_USER@$IP 'sudo systemctl status geant4-coordinator'
  curl http://$IP:8000/api/v1/health

Apuntar los workers a:
  COORDINATOR_URL=http://$IP:8000

IMPORTANTE (ver AGENTS.md, riesgos aceptados): sin autenticacion de
workers todavia. El puerto 8000 quedo abierto a cualquier IP -- para
un uso mas que de prueba, restringir con:
  az vm open-port --resource-group $RESOURCE_GROUP --name $VM_NAME \\
    --port 8000 --priority 900 --source-address-prefixes <tu-ip>/32

Para destruir todo cuando termines (borra la VM y TODOS sus recursos,
incluida cualquier corrida en curso en el coordinator -- la base SQLite
y los resultados subidos se pierden si no se respaldaron antes):
  az group delete --name $RESOURCE_GROUP --yes --no-wait
==================================================================
EOF
