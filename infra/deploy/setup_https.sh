#!/usr/bin/env bash
# Instala Caddy como reverse proxy con TLS automatico (Let's Encrypt)
# delante del coordinator, en una VM YA EXISTENTE (no recrea nada, para
# no interrumpir a los workers ya conectados). El coordinator sigue
# escuchando HTTP en localhost:8000 sin cambios; Caddy expone HTTPS al
# mundo en el dominio dado y reenvia internamente.
#
# Correr DENTRO de la VM del coordinator (via ssh o gcloud compute ssh),
# como root o con sudo. Requiere que el registro DNS tipo A del dominio
# ya apunte a la IP publica de esta VM (Let's Encrypt valida contra eso).
#
# Uso:
#   sudo bash setup_https.sh coordinator.vlaboratory.org
set -euo pipefail

DOMAIN="${1:?Uso: sudo bash setup_https.sh <dominio>, ej. coordinator.vlaboratory.org}"

[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo." >&2; exit 1; }
[[ ${#DOMAIN} -le 253 && "$DOMAIN" =~ ^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$ ]] || {
  echo "Dominio DNS invalido." >&2; exit 1;
}
echo "==> Verificando que $DOMAIN resuelva a la IP de esta VM..."
MY_IP="$(curl -fsS -4 --max-time 15 https://ifconfig.me || curl -fsS -4 --max-time 15 https://icanhazip.com)"
[[ "$MY_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "IP publica invalida" >&2; exit 1; }
DOMAIN_IP="$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | sort -u || true)"
if ! grep -Fxq "$MY_IP" <<< "$DOMAIN_IP"; then
  echo "ERROR: $DOMAIN no apunta a $MY_IP (IPv4 obtenidas: $DOMAIN_IP)." >&2
  exit 1
fi
echo "OK: $DOMAIN -> $MY_IP"

echo "==> Instalando Caddy (repo oficial)"
apt-get update -y
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -y
apt-get install -y caddy

echo "==> Configurando Caddy (proxy HTTPS -> coordinator local en :8000)"
cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:8000
}
EOF

echo "==> Abriendo puertos 80/443 en el firewall de GCP (si no estan abiertos ya)"
# No falla el script si la regla ya existe -- idempotente, igual que el
# resto de scripts de infra/deploy/.
if command -v gcloud >/dev/null 2>&1; then
  if ! gcloud compute firewall-rules describe geant4-coordinator-allow-https >/dev/null 2>&1; then
    gcloud compute firewall-rules create geant4-coordinator-allow-https \
    --allow=tcp:80,tcp:443 --target-tags=geant4-coordinator
  fi
else
  echo "AVISO: gcloud no disponible en esta VM -- si el firewall bloquea 80/443, crea la regla desde tu maquina:"
  echo "  gcloud compute firewall-rules create geant4-coordinator-allow-https --allow=tcp:80,tcp:443 --target-tags=geant4-coordinator"
fi

caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl restart caddy
systemctl enable caddy

echo ""
echo "=================================================================="
echo " Caddy instalado. Verificando el certificado (puede tardar ~30s"
echo " la primera vez mientras Let's Encrypt lo emite)..."
sleep 10
if curl -sf "https://$DOMAIN/api/v1/health" > /dev/null; then
  echo " OK: https://$DOMAIN/api/v1/health responde."
else
  echo " Todavia no responde -- revisa 'journalctl -u caddy -f' para ver"
  echo " el progreso de la emision del certificado."
fi
echo ""
echo " A partir de ahora, usa https://$DOMAIN en vez de http://<ip>:8000"
echo " en COORDINATOR_URL de los workers. El puerto 8000 sigue abierto"
echo " directamente (HTTP, sin cifrar) -- considera cerrarlo despues de"
echo " migrar todos los workers, con:"
echo "   gcloud compute firewall-rules delete geant4-coordinator-allow-8000"
echo "=================================================================="
