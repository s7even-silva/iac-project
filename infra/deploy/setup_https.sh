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

echo "==> Verificando que $DOMAIN resuelva a la IP de esta VM..."
MY_IP="$(curl -s -4 ifconfig.me || curl -s -4 icanhazip.com)"
DOMAIN_IP="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)"
if [[ -z "$DOMAIN_IP" ]]; then
  echo "ERROR: $DOMAIN no resuelve todavia (DNS sin propagar, o registro mal creado)." >&2
  exit 1
fi
if [[ "$DOMAIN_IP" != "$MY_IP" ]]; then
  echo "ERROR: $DOMAIN resuelve a $DOMAIN_IP, pero esta VM es $MY_IP -- revisa el registro DNS." >&2
  exit 1
fi
echo "OK: $DOMAIN -> $MY_IP"

echo "==> Instalando Caddy (repo oficial)"
apt-get update -y
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
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
  gcloud compute firewall-rules create geant4-coordinator-allow-https \
    --allow=tcp:80,tcp:443 --target-tags=geant4-coordinator 2>&1 | grep -v "already exists" || true
else
  echo "AVISO: gcloud no disponible en esta VM -- si el firewall bloquea 80/443, crea la regla desde tu maquina:"
  echo "  gcloud compute firewall-rules create geant4-coordinator-allow-https --allow=tcp:80,tcp:443 --target-tags=geant4-coordinator"
fi

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
