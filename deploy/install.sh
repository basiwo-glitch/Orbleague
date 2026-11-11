#!/usr/bin/env bash
# Einmal-Installation auf Debian 12/13 oder Ubuntu 22.04/24.04, als root:
#   bash /opt/orbleague/deploy/install.sh <domain>
# Erneut ausführen ist gefahrlos (die .env bleibt erhalten).
set -euo pipefail
DOMAIN="${1:?Domain angeben, z.B. v123.quicksrv.de}"
APP=/opt/orbleague
SRC="$(cd "$(dirname "$0")/.." && pwd)"
export DEBIAN_FRONTEND=noninteractive

echo "==> Pakete installieren"
apt-get update -q
apt-get install -y -q python3 python3-pil python3-numpy ffmpeg caddy git tzdata ca-certificates
timedatectl set-timezone Europe/Berlin 2>/dev/null || true

echo "==> Programm einrichten"
id orbleague >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin orbleague
if [ "$SRC" != "$APP" ]; then mkdir -p "$APP"; cp -a "$SRC"/. "$APP"/; fi
git config --system --add safe.directory "$APP" || true
cd "$APP"
if [ ! -f .env ]; then
  cp .env.example .env
  PW="$(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
  sed -i "s#^PUBLIC_URL=.*#PUBLIC_URL=https://$DOMAIN#; s#^DASHBOARD_PASSWORD=.*#DASHBOARD_PASSWORD=$PW#" .env
  echo "WEB_HOST=127.0.0.1" >> .env
fi
chmod 600 .env
chown -R orbleague:orbleague "$APP"

echo "==> Selbsttest (rendert kein Video, prüft nur Abhängigkeiten)"
runuser -u orbleague -- python3 -c "import viralai.web, viralai.orchestrator; from viralai.render import engine; print('ok')" \
  || { echo "Selbsttest fehlgeschlagen"; exit 1; }

echo "==> HTTPS + Dienst starten"
sed "s/orbleague.deinedomain.de/$DOMAIN/" deploy/Caddyfile > /etc/caddy/Caddyfile
cp deploy/orbleague.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now orbleague
systemctl enable caddy >/dev/null 2>&1 || true
systemctl restart caddy
sleep 3
systemctl is-active --quiet orbleague && echo "ORB LEAGUE läuft." || { journalctl -u orbleague -n 30 --no-pager; exit 1; }

echo
echo "============================================================"
echo " Dashboard:  https://$DOMAIN"
echo " Benutzer:   admin"
echo " Passwort:   $(grep '^DASHBOARD_PASSWORD=' .env | cut -d= -f2)"
echo "============================================================"
